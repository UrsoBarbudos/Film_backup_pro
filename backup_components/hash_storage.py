"""
Модуль для работы с хранилищем хешей файлов.
Реализует оптимизированное хранилище с инкрементальным сохранением,
сжатием и потоковым чтением для больших файлов.
"""

import json
import gzip
import atexit
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from interfaces import IConfig, IFileSystemInterface
from .retry_handler import RetryHandler
from .exceptions import BackupCancelledError
from .control_tokens import CancelToken


logger = logging.getLogger(__name__)


class HashStorage:
    """Класс для работы с хранилищем хешей файлов"""
    
    # Фиксированные параметры оптимизации
    AUTO_SAVE_THRESHOLD = 100  # Количество изменений перед автосохранением
    AUTO_SAVE_INTERVAL = 30  # Интервал автосохранения в секундах
    STREAMING_THRESHOLD = 50 * 1024 * 1024  # 50MB порог для потокового чтения

    @staticmethod
    def _strip_extensions(path: str) -> str:
        if path.endswith(".json.gz"):
            return path[:-8]
        if path.endswith(".json"):
            return path[:-5]
        if path.endswith(".gz"):
            return path[:-3]
        return path
    
    def __init__(
        self,
        config: Optional[IConfig] = None,
        storage_path: Optional[str] = None,
        file_system: Optional[IFileSystemInterface] = None,
        cancel_token: Optional[CancelToken] = None,
        log_callback: Optional[Any] = None
    ):
        """
        Инициализация хранилища хешей
        
        :param config: Экземпляр Config для получения настроек (опционально)
        :param storage_path: Путь к файлу хранилища (опционально, по умолчанию ~/.film_backup_pro_hashes.json)
        :param file_system: Интерфейс файловой системы (обязателен для I/O операций)
        :param cancel_token: CancelToken для проверки отмены (опционально)
        :param log_callback: Функция для логирования (опционально)
        """
        if file_system is None:
            raise ValueError("file_system must be provided to HashStorage (explicit DI).")

        self._file_system = file_system

        # Определяем путь к файлу хранилища
        if storage_path is None:
            # Базовое имя файла без расширения, расширение добавится при сохранении.
            # Важно: используем app data dir для переносимости/прав доступа.
            from paths import get_app_data_dir

            app_data_dir = get_app_data_dir()
            self._file_system.makedirs(app_data_dir, exist_ok=True)
            storage_path = self._file_system.join(app_data_dir, "film_backup_pro_hashes")

        # Базовый путь (без расширения). Пользователь мог передать и с расширением — нормализуем.
        self._base_storage_path = self._strip_extensions(str(storage_path))
        # Текущий путь к файлу (с расширением .json или .json.gz), выбирается при _load() / _save_unlocked()
        self.storage_path: Optional[str] = None
        self.config = config
        self.cancel_token = cancel_token
        self.log_callback = log_callback or (lambda msg: None)
        
        # Инициализируем RetryHandler для обработки временных ошибок
        self.retry_handler = RetryHandler(
            max_attempts=3,
            delay=1.0,
            log_callback=self.log_callback
        )
        
        # Сжатие файла хранилища хешей всегда включено (gzip, ~60–80% экономии места)
        self.use_compression = True
        
        # Данные хранилища
        self._data: Dict[str, Any] = {}
        self._changes_count = 0
        self._dirty = False
        self._lock = threading.Lock()
        self._auto_save_timer: Optional[threading.Timer] = None
        
        # Загружаем существующие данные
        self._load()
        
        # Запускаем таймер автосохранения
        self._start_auto_save_timer()
        
        # Регистрируем сохранение при завершении
        atexit.register(self._save_on_exit)
    
    def _load(self) -> None:
        """Загружает данные из файла с поддержкой сжатия и потокового чтения"""
        base_path_str = self._base_storage_path

        json_path = base_path_str + ".json"
        json_gz_path = base_path_str + ".json.gz"

        is_compressed = False
        file_path: Optional[str] = None

        if self._file_system.exists(json_gz_path):
            file_path = json_gz_path
            is_compressed = True
        elif self._file_system.exists(json_path):
            file_path = json_path
            is_compressed = False
        else:
            # Файл не существует, создаем пустое хранилище
            self._data = {
                "version": "1.0",
                "last_save": None,
                "use_compression": self.use_compression,
                "files": {},
                "hash_index": {}
            }
            return
        
        # Обновляем путь к файлу
        self.storage_path = file_path
        
        try:
            # Определяем размер файла для выбора метода чтения
            file_size = self._file_system.getsize(file_path)
            
            # Если файл большой, используем потоковое чтение
            if file_size > self.STREAMING_THRESHOLD:
                self._load_streaming(is_compressed)
            else:
                self._load_normal(is_compressed)
                
        except Exception as e:
            logger.warning("Не удалось загрузить хранилище хешей: %s", e)
            # Создаем пустое хранилище при ошибке
            self._data = {
                "version": "1.0",
                "last_save": None,
                "use_compression": self.use_compression,
                "files": {},
                "hash_index": {}
            }
    
    def _load_normal(self, is_compressed: bool) -> None:
        """Обычное чтение для маленьких файлов"""
        try:
            if not self.storage_path:
                raise FileNotFoundError("HashStorage storage_path is not set")
            if is_compressed:
                with self._file_system.open(self.storage_path, 'rb') as raw:
                    with gzip.open(raw, 'rt', encoding='utf-8') as f:
                        self._data = json.load(f)
            else:
                with self._file_system.open(self.storage_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            
            # Инициализируем структуру если отсутствует
            if 'files' not in self._data:
                self._data['files'] = {}
            if 'hash_index' not in self._data:
                self._data['hash_index'] = {}
            if 'version' not in self._data:
                self._data['version'] = "1.0"
            if 'use_compression' not in self._data:
                self._data['use_compression'] = self.use_compression
                
        except Exception as e:
            logger.warning("Ошибка при обычном чтении хранилища: %s", e)
            raise
    
    def _load_streaming(self, is_compressed: bool) -> None:
        """Потоковое чтение для больших файлов через ijson"""
        try:
            import ijson  # type: ignore
            if not self.storage_path:
                raise FileNotFoundError("HashStorage storage_path is not set")
            
            # Инициализируем структуру
            self._data = {
                "version": "1.0",
                "last_save": None,
                "use_compression": self.use_compression,
                "files": {},
                "hash_index": {}
            }
            
            if is_compressed:
                with self._file_system.open(self.storage_path, 'rb') as raw:
                    with gzip.open(raw, 'rb') as file_obj:
                        parser = ijson.parse(file_obj)
                        current_file_path = None
                        current_hash = None

                        for prefix, event, value in parser:
                            if prefix == 'files' and event == 'map_key':
                                current_file_path = value
                                self._data['files'][current_file_path] = {}
                            elif prefix.startswith('files.') and current_file_path:
                                key = prefix.split('.')[-1]
                                if event == 'string' or event == 'number':
                                    self._data['files'][current_file_path][key] = value
                            elif prefix == 'hash_index' and event == 'map_key':
                                current_hash = value
                                self._data['hash_index'][current_hash] = []
                            elif prefix.startswith('hash_index.') and current_hash is not None:
                                if event == 'string':
                                    if value not in self._data['hash_index'][current_hash]:
                                        self._data['hash_index'][current_hash].append(value)
                            elif prefix == 'version' and event == 'string':
                                self._data['version'] = value
                            elif prefix == 'last_save' and event == 'string':
                                self._data['last_save'] = value
                            elif prefix == 'use_compression' and event == 'boolean':
                                self._data['use_compression'] = value
            else:
                with self._file_system.open(self.storage_path, 'rb') as file_obj:
                    parser = ijson.parse(file_obj)
                    current_file_path = None
                    current_hash = None

                    for prefix, event, value in parser:
                        if prefix == 'files' and event == 'map_key':
                            current_file_path = value
                            self._data['files'][current_file_path] = {}
                        elif prefix.startswith('files.') and current_file_path:
                            key = prefix.split('.')[-1]
                            if event == 'string' or event == 'number':
                                self._data['files'][current_file_path][key] = value
                        elif prefix == 'hash_index' and event == 'map_key':
                            current_hash = value
                            self._data['hash_index'][current_hash] = []
                        elif prefix.startswith('hash_index.') and current_hash is not None:
                            if event == 'string':
                                if value not in self._data['hash_index'][current_hash]:
                                    self._data['hash_index'][current_hash].append(value)
                        elif prefix == 'version' and event == 'string':
                            self._data['version'] = value
                        elif prefix == 'last_save' and event == 'string':
                            self._data['last_save'] = value
                        elif prefix == 'use_compression' and event == 'boolean':
                            self._data['use_compression'] = value
                
        except ImportError:
            # Если ijson не установлен, fallback на обычное чтение
            logger.warning("ijson не установлен, используется обычное чтение")
            self._load_normal(is_compressed)
        except Exception as e:
            logger.warning("Ошибка при потоковом чтении хранилища: %s", e)
            # Fallback на обычное чтение
            try:
                self._load_normal(is_compressed)
            except Exception:
                # Если и это не помогло, создаем пустое хранилище
                self._data = {
                    "version": "1.0",
                    "last_save": None,
                    "use_compression": self.use_compression,
                    "files": {},
                    "hash_index": {}
                }
    
    def _cleanup_temp_files(self, base_path: Optional[str] = None) -> None:
        """
        Очищает временные файлы для указанного базового пути
        
        :param base_path: Путь (base или с расширением). Если None, используется базовый путь.
        """
        base_path_str = self._strip_extensions(base_path or self._base_storage_path)
        
        # Очищаем временные файлы для обоих форматов
        temp_paths = [
            base_path_str + ".json.tmp",
            base_path_str + ".json.gz.tmp",
        ]
        
        for temp_path in temp_paths:
            if self._file_system.exists(temp_path):
                try:
                    self._file_system.remove(temp_path)
                    self.log_callback(f"🗑️  Удален временный файл: {self._file_system.basename(temp_path)}")
                except Exception as e:
                    logger.warning("Не удалось удалить временный файл %s: %s", temp_path, e)
    
    def _save(self) -> None:
        """Сохраняет данные с инкрементальным сохранением и атомарной записью (получает блокировку)"""
        logger.debug("HashStorage._save() entry (dirty=%s)", self._dirty)
        # Проверка отмены перед сохранением
        if self.cancel_token:
            self.cancel_token.raise_if_cancelled("Сохранение отменено пользователем")
        
        with self._lock:
            self._save_unlocked()
    
    def _save_unlocked(self) -> None:
        """Сохраняет данные с инкрементальным сохранением и атомарной записью (без получения блокировки, предполагается что блокировка уже удерживается)"""
        logger.debug("HashStorage._save_unlocked() entry (dirty=%s)", self._dirty)
        if not self._dirty:
            return
        
        try:
            base_path_str = self._base_storage_path
            
            # Формируем путь с правильным расширением
            if self.use_compression:
                storage_path = base_path_str + ".json.gz"
            else:
                storage_path = base_path_str + ".json"
            
            # Обновляем метаданные
            self._data['last_save'] = datetime.now().isoformat()
            self._data['use_compression'] = self.use_compression
            
            # Создаем временный файл для атомарной записи
            temp_path = storage_path + ".tmp"
            
            # Очищаем старые временные файлы перед созданием новых
            self._cleanup_temp_files(storage_path)
            
            try:
                # Проверка отмены перед записью
                if self.cancel_token:
                    self.cancel_token.raise_if_cancelled("Сохранение отменено пользователем")
                
                # Записываем во временный файл (с повторными попытками)
                def write_temp_file():
                    if self.use_compression:
                        with self._file_system.open(temp_path, 'wb') as raw:
                            with gzip.open(raw, 'wt', encoding='utf-8') as f:
                                json.dump(self._data, f, indent=2, ensure_ascii=False)
                    else:
                        with self._file_system.open(temp_path, 'w', encoding='utf-8') as f:
                            json.dump(self._data, f, indent=2, ensure_ascii=False)
                
                self.retry_handler.retry_on_temporary_error(write_temp_file)
                
                # Проверка отмены перед атомарной заменой
                if self.cancel_token and self.cancel_token.is_cancelled():
                    # Очищаем временный файл перед отменой
                    self._cleanup_temp_files(storage_path)
                    raise BackupCancelledError("Сохранение отменено пользователем")
                
                # Атомарная замена (с повторными попытками)
                self.retry_handler.retry_on_temporary_error(lambda: self._file_system.replace(temp_path, storage_path))
                
                # Обновляем путь
                self.storage_path = storage_path
                
                # Удаляем старый файл если формат изменился
                base_path_str = self._strip_extensions(storage_path)
                
                # Проверяем и удаляем файл с другим расширением
                if self.use_compression:
                    # Если сохраняем со сжатием, удаляем несжатый файл
                    old_path = base_path_str + ".json"
                    if self._file_system.exists(old_path) and old_path != storage_path:
                        try:
                            self._file_system.remove(old_path)
                        except Exception:
                            pass
                else:
                    # Если сохраняем без сжатия, удаляем сжатый файл
                    old_path = base_path_str + ".json.gz"
                    if self._file_system.exists(old_path) and old_path != storage_path:
                        try:
                            self._file_system.remove(old_path)
                        except Exception:
                            pass
                
                self._dirty = False
                self._changes_count = 0
                
                # Очищаем временные файлы после успешной записи
                self._cleanup_temp_files(storage_path)
                
            except BackupCancelledError:
                # Очищаем временный файл при отмене
                self._cleanup_temp_files(storage_path)
                raise
            except Exception:
                # Очищаем временный файл при ошибке
                self._cleanup_temp_files(storage_path)
                raise
                
        except BackupCancelledError:
            # Важно: отмену пробрасываем наверх, чтобы вызывающий код мог корректно остановиться.
            raise
        except Exception as e:
            # Не валим приложение из-за невозможности сохранить хеши, но логируем.
            logger.warning("Не удалось сохранить хранилище хешей: %s", e)
    
    def _start_auto_save_timer(self) -> None:
        """Запускает таймер периодического сохранения"""
        def auto_save():
            if self._dirty:
                self._save()
            # Перезапускаем таймер
            self._auto_save_timer = threading.Timer(self.AUTO_SAVE_INTERVAL, auto_save)
            self._auto_save_timer.daemon = True
            self._auto_save_timer.start()
        
        self._auto_save_timer = threading.Timer(self.AUTO_SAVE_INTERVAL, auto_save)
        self._auto_save_timer.daemon = True
        self._auto_save_timer.start()
    
    def _save_on_exit(self) -> None:
        """Сохраняет данные при завершении работы приложения"""
        if self._dirty:
            try:
                self._save()
            except BackupCancelledError:
                # Игнорируем отмену при завершении
                pass
        
        # Очищаем временные файлы при завершении
        self.cleanup_temp_files()
    
    def cleanup_temp_files(self) -> None:
        """Публичный метод для очистки временных файлов (вызывается извне)"""
        self._cleanup_temp_files()
    
    def set_hash(
        self,
        file_path: str,
        hash_value: str,
        size: Optional[int] = None,
        modified_time: Optional[str] = None,
        destination_path: Optional[str] = None
    ) -> None:
        """
        Сохраняет хеш файла с метаданными
        
        :param file_path: Путь к файлу
        :param hash_value: MD5 хеш файла
        :param size: Размер файла в байтах (опционально)
        :param modified_time: Время модификации файла в ISO формате (опционально)
        :param destination_path: Путь к файлу в назначении (опционально)
        """
        logger.debug("HashStorage.set_hash() entry (file_path=%s)", file_path)
        with self._lock:
            # Инициализируем структуру если отсутствует
            if 'files' not in self._data:
                self._data['files'] = {}
            if 'hash_index' not in self._data:
                self._data['hash_index'] = {}
            
            # Обновляем данные файла
            self._data['files'][file_path] = {
                'hash': hash_value,
                'size': size,
                'modified': modified_time,
                'created': datetime.now().isoformat(),
                'destination': destination_path
            }
            
            # Обновляем индекс хешей
            if hash_value not in self._data['hash_index']:
                self._data['hash_index'][hash_value] = []
            if file_path not in self._data['hash_index'][hash_value]:
                self._data['hash_index'][hash_value].append(file_path)
            
            self._dirty = True
            self._changes_count += 1
            
            # Автосохранение при достижении порога
            if self._changes_count >= self.AUTO_SAVE_THRESHOLD:
                # Вызываем _save_unlocked() так как блокировка уже удерживается
                self._save_unlocked()
                logger.debug("HashStorage.set_hash(): autosave executed (changes_count=%d)", self._changes_count)
        logger.debug("HashStorage.set_hash() exit (file_path=%s)", file_path)
    
    def get_hash(self, file_path: str) -> Optional[str]:
        """
        Получает хеш файла
        
        :param file_path: Путь к файлу
        :return: Хеш файла или None если не найден
        """
        with self._lock:
            if file_path in self._data.get('files', {}):
                return self._data['files'][file_path].get('hash')
            return None

    def get_sample_signature(self, file_path: str, *, chunk_size_bytes: int) -> Optional[str]:
        """
        Возвращает sample_signature для файла, если он сохранён с теми же параметрами.

        :param file_path: путь к файлу
        :param chunk_size_bytes: размер чанка, использованный при вычислении sample_signature
        """
        with self._lock:
            entry = self._data.get("files", {}).get(file_path)
            if not isinstance(entry, dict):
                return None
            sig = entry.get("sample_sig")
            params = entry.get("sample_sig_params")
            if not sig or not isinstance(params, dict):
                return None
            if params.get("chunk_size_bytes") != int(chunk_size_bytes):
                return None
            return str(sig)

    def set_sample_signature(
        self,
        *,
        file_path: str,
        sample_sig: str,
        chunk_size_bytes: int,
    ) -> None:
        """
        Сохраняет sample_signature для файла (и параметры вычисления).
        """
        with self._lock:
            if "files" not in self._data:
                self._data["files"] = {}
            entry = self._data["files"].get(file_path)
            if not isinstance(entry, dict):
                entry = {}
            entry["sample_sig"] = sample_sig
            entry["sample_sig_params"] = {"chunk_size_bytes": int(chunk_size_bytes)}
            self._data["files"][file_path] = entry

            self._dirty = True
            self._changes_count += 1

            if self._changes_count >= self.AUTO_SAVE_THRESHOLD:
                self._save_unlocked()

    def force_save(self) -> None:
        """Принудительно сохраняет данные (используется при критических операциях)"""
        with self._lock:
            self._dirty = True
            self._save_unlocked()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику хранилища
        
        :return: Словарь со статистикой
        """
        with self._lock:
            return {
                'total_files': len(self._data.get('files', {})),
                'total_hashes': len(self._data.get('hash_index', {})),
                'last_save': self._data.get('last_save'),
                'use_compression': self._data.get('use_compression', self.use_compression),
                'pending_changes': self._changes_count,
                'dirty': self._dirty
            }
