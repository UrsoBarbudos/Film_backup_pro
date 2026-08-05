"""
Модуль для копирования файлов в процессе резервного копирования.
Отвечает только за копирование файлов без проверки целостности.
"""

import time
import threading
import hashlib
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING
from interfaces import IFileSystemInterface
from .control_tokens import CancelToken, PauseToken
from .copy_verification_result import CopyVerificationResult
from .operation_issue import OperationIssueCode, create_message_issue, create_operation_issue
from .operation_results import CopyResult


logger = logging.getLogger(__name__)


class _CopyStageError(Exception):
    """Сохраняет точный этап внутренней файловой операции до общего catch."""

    def __init__(self, stage: str, original: BaseException):
        super().__init__(str(original))
        self.stage = stage
        self.original = original

# Поддержка как относительных, так и абсолютных импортов для работы при прямом запуске
try:
    from .copy_strategy import CopyMethod, get_copy_method
    from .exceptions import BackupCancelledError
    from .retry_handler import RetryHandler
except ImportError:
    # Fallback для прямого запуска модуля
    from backup_components.copy_strategy import CopyMethod, get_copy_method
    from backup_components.exceptions import BackupCancelledError
    from backup_components.retry_handler import RetryHandler

if TYPE_CHECKING:
    try:
        from .hash_storage import HashStorage
    except ImportError:
        from backup_components.hash_storage import HashStorage


class FileCopier:
    """Класс для копирования файлов"""
    
    def __init__(
        self, 
        log_callback: Optional[Callable[[str], None]] = None,
        file_system: Optional[IFileSystemInterface] = None,
        pause_event: Optional[threading.Event] = None,
        pause_token: Optional[PauseToken] = None,
        cancel_token: Optional[CancelToken] = None,
        hash_storage: Optional['HashStorage'] = None,
        verification_mode: str = "full",
        verification_run_id: Optional[str] = None,
    ):
        """
        Инициализация копировщика файлов
        
        :param log_callback: Функция для логирования операций
        :param file_system: Интерфейс файловой системы (опционально, для обратной совместимости)
        :param pause_event: threading.Event для управления паузой (опционально)
        :param pause_token: PauseToken для управления паузой (опционально)
        :param cancel_token: CancelToken для управления отменой (опционально)
        :param hash_storage: Хранилище хешей для сохранения вычисленных хешей (опционально)
        """
        self.log_callback = log_callback or (lambda msg: None)
        self.fs = file_system
        self.pause_event = pause_event
        self.pause_token = pause_token or (PauseToken(pause_event) if pause_event is not None else None)
        self.cancel_token = cancel_token
        self.hash_storage = hash_storage
        self.verification_mode = verification_mode
        self.verification_run_id = verification_run_id or uuid.uuid4().hex
        self.verification_read_bytes = 0
        
        # Инициализируем RetryHandler для обработки временных ошибок
        self.retry_handler = RetryHandler(
            max_attempts=3,
            delay=1.0,
            log_callback=self.log_callback
        )

        if self.fs is None:
            raise ValueError("file_system must be provided to FileCopier (explicit DI).")
    
    def _copy_with_shutil(
        self,
        source_path: str,
        destination_path: str
    ) -> Optional[str]:
        """
        Копирует файл блоками для файлов 0-100 МБ.
        Вычисляет MD5 хеш исходного файла во время копирования (оптимизировано - без двойного чтения).
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :return: MD5 хеш исходного файла или None если вычисление не требуется
        """
        # Для файлов до 100 МБ используем размер блока 1 МБ
        # Это оптимально для баланса между производительностью и использованием памяти
        block_size = 1 * 1024 * 1024  # 1 МБ
        
        # Инициализируем MD5 хеш для вычисления во время копирования
        hash_md5 = hashlib.md5()
        
        # Открываем файлы с повторными попытками при временных ошибках
        try:
            src_file = self.retry_handler.retry_on_temporary_error(
                self.fs.open, source_path, 'rb'
            )
        except Exception as exc:
            raise _CopyStageError("copy.read_source", exc) from exc
        try:
            dst_file = self.retry_handler.retry_on_temporary_error(
                self.fs.open, destination_path, 'wb'
            )
        except Exception as exc:
            raise _CopyStageError("copy.write_temporary_file", exc) from exc
        
        with src_file as src, dst_file as dst:
            while True:
                # Проверка отмены перед чтением следующего блока
                if self.cancel_token:
                    self.cancel_token.raise_if_cancelled("Копирование отменено пользователем")
                
                try:
                    chunk = src.read(block_size)
                except Exception as exc:
                    raise _CopyStageError("copy.read_source", exc) from exc
                if not chunk:
                    break
                
                # Вычисляем хеш во время чтения блока
                hash_md5.update(chunk)
                
                # Записываем блок в файл назначения
                try:
                    dst.write(chunk)
                except Exception as exc:
                    raise _CopyStageError("copy.write_temporary_file", exc) from exc

            try:
                self.fs.fsync_file(dst)
            except Exception as exc:
                raise _CopyStageError("copy.fsync_temporary_file", exc) from exc
        
        # Копируем метаданные (с повторными попытками при временных ошибках)
        try:
            self.retry_handler.retry_on_temporary_error(
                self.fs.copystat, source_path, destination_path
            )
        except Exception as exc:
            raise _CopyStageError("copy.write_temporary_file", exc) from exc
        
        # Возвращаем вычисленный хеш
        return hash_md5.hexdigest()
    
    def _copy_with_blocks(
        self,
        source_path: str,
        destination_path: str,
        source_size: int,
        progress_callback: Optional[Callable] = None,
        base_copied_bytes: int = 0,
        total_bytes: int = 0
    ) -> Optional[str]:
        """
        Копирует файл блоками с адаптивным размером блока в зависимости от размера файла.
        Вычисляет MD5 хеш исходного файла во время копирования.
        
        Размеры блоков:
        - 10 МБ для файлов 100 МБ - 10 GB
        - 15 МБ для файлов 10 GB - 50 GB
        - 20 МБ для файлов >50 GB
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param source_size: Размер исходного файла в байтах
        :param progress_callback: Callback для обновления прогресса (опционально)
        :param base_copied_bytes: Базовое количество скопированных байт для расчета прогресса
        :param total_bytes: Общий объем данных для расчета прогресса
        :return: MD5 хеш исходного файла или None если вычисление не требуется
        """
        # Многоуровневая система размеров блоков в зависимости от размера файла
        if source_size > 50 * 1024 * 1024 * 1024:  # >50 GB
            block_size = 20 * 1024 * 1024  # 20 МБ для очень больших файлов
        elif source_size > 10 * 1024 * 1024 * 1024:  # >10 GB
            block_size = 15 * 1024 * 1024  # 15 МБ для больших файлов
        else:
            block_size = 10 * 1024 * 1024  # 10 МБ для обычных больших файлов
        
        copied_in_file = 0
        start_time = time.time()
        last_update_time = start_time
        last_copied_for_speed = 0
        update_interval = 0.1  # Обновляем каждые 100мс для более плавного отображения
        
        # Инициализируем MD5 хеш для вычисления во время копирования
        hash_md5 = hashlib.md5()
        
        # Импортируем функцию безопасного сложения
        from utils import safe_add_bytes
        
        # Открываем файлы с повторными попытками при временных ошибках
        try:
            src_file = self.retry_handler.retry_on_temporary_error(
                self.fs.open, source_path, 'rb'
            )
        except Exception as exc:
            raise _CopyStageError("copy.read_source", exc) from exc
        try:
            dst_file = self.retry_handler.retry_on_temporary_error(
                self.fs.open, destination_path, 'wb'
            )
        except Exception as exc:
            raise _CopyStageError("copy.write_temporary_file", exc) from exc
        with src_file as src, dst_file as dst:
            logger.debug(
                "_copy_with_blocks: entering copy loop (source_path=%s, source_size=%d, block_size=%d)",
                source_path,
                source_size,
                block_size,
            )
            iteration_count = 0
            while True:
                iteration_count += 1
                # Проверка отмены перед чтением следующего блока
                if self.cancel_token:
                    self.cancel_token.raise_if_cancelled("Копирование отменено пользователем")
                
                try:
                    chunk = src.read(block_size)
                except Exception as exc:
                    raise _CopyStageError("copy.read_source", exc) from exc
                if not chunk:
                    break
                
                # Вычисляем хеш во время чтения блока
                hash_md5.update(chunk)
                
                # Записываем блок в файл назначения
                try:
                    dst.write(chunk)
                except Exception as exc:
                    raise _CopyStageError("copy.write_temporary_file", exc) from exc
                copied_in_file += len(chunk)
                
                # Проверка паузы после записи блока
                if self.pause_token and self.pause_token.is_paused():
                    self.pause_token.wait_if_paused(self.cancel_token)
                
                # Обновляем прогресс периодически
                if progress_callback:
                    current_time = time.time()
                    if current_time - last_update_time >= update_interval:
                        # Используем безопасное сложение для защиты от переполнения
                        current_copied = safe_add_bytes(base_copied_bytes, copied_in_file)
                        percent = (
                            min(99, int(current_copied / total_bytes * 100))
                            if total_bytes > 0
                            else 0
                        )
                        # Вычисляем скорость на основе скопированного с последнего обновления
                        elapsed = current_time - last_update_time
                        bytes_delta = copied_in_file - last_copied_for_speed
                        if elapsed > 0 and bytes_delta > 0:
                            speed_mbps = (bytes_delta / (1024 * 1024)) / elapsed
                        else:
                            # Если нет данных для расчета скорости, используем среднюю скорость
                            total_elapsed = current_time - start_time
                            if total_elapsed > 0:
                                speed_mbps = (copied_in_file / (1024 * 1024)) / total_elapsed
                            else:
                                speed_mbps = 0.0
                        progress_callback(percent, current_copied, total_bytes, speed_mbps, source_path)
                        last_update_time = current_time
                        last_copied_for_speed = copied_in_file
            
            try:
                self.fs.fsync_file(dst)
            except Exception as exc:
                raise _CopyStageError("copy.fsync_temporary_file", exc) from exc
        
        # Копируем метаданные (с повторными попытками при временных ошибках)
        try:
            self.retry_handler.retry_on_temporary_error(
                self.fs.copystat, source_path, destination_path
            )
        except Exception as exc:
            raise _CopyStageError("copy.write_temporary_file", exc) from exc
        
        # Возвращаем вычисленный хеш
        return hash_md5.hexdigest()
    
    def copy_file(
        self,
        source_path: str,
        destination_path: str,
        destination_root: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        base_copied_bytes: int = 0,
        total_bytes: int = 0
    ) -> CopyResult:
        """
        Копирует один файл и в полном режиме проверяет MD5 временной копии.
        Перед копированием проверяет существование файла в назначении и сравнивает размер.
        Вычисляет MD5 хеш исходного файла во время копирования.
        Вызывает log_callback для статуса операций.
        Возвращает кортеж с успехом, размером и доказательством текущей проверки.
        Размер файла возвращается в байтах, даже если файл был пропущен (уже существует).
        Доказательство возвращается только после успешной полной проверки и replace.
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param destination_root: Корневая директория назначения (опционально)
        :param progress_callback: Callback для обновления прогресса (опционально)
        :param base_copied_bytes: Базовое количество скопированных байт для расчета прогресса
        :param total_bytes: Общий объем данных для расчета прогресса
        :return: Структурированный результат копирования
        """
        logger.debug("copy_file() entry (source=%s, destination=%s)", source_path, destination_path)
        # Проверка отмены перед началом копирования
        if self.cancel_token:
            self.cancel_token.raise_if_cancelled("Копирование отменено пользователем")
        
        temp_path: Optional[str] = None
        verification_result: Optional[CopyVerificationResult] = None
        operation_stage = "copy.source_metadata"
        try:
            # Проверяем существование исходного файла (с повторными попытками)
            if not self.retry_handler.retry_on_temporary_error(
                self.fs.exists, source_path
            ):
                error_msg = f"❌ Исходный файл не найден: {source_path}"
                logger.error("%s", error_msg)
                self.log_callback(error_msg)
                return CopyResult(
                    success=False,
                    copied_size=0,
                    issue=create_message_issue(
                        stage="copy.source_metadata",
                        code=OperationIssueCode.SOURCE_NOT_FOUND,
                        message="Исходный файл не найден",
                        source_path=source_path,
                        destination_path=destination_path,
                        file_name=self.fs.basename(source_path),
                    ),
                )
            
            # Получаем размер и имя файла (с повторными попытками)
            source_size = self.retry_handler.retry_on_temporary_error(
                self.fs.getsize, source_path
            )
            source_modified_ns = self._get_modified_ns(source_path)
            filename = self.fs.basename(source_path)
            
            # Решение о замене/пропуске/оставить оба принимается в CopyPlanAndExecuteService через диалог.
            # Сюда передаётся только путь для копирования (при replace — существующий, при keep_both — новый).
            operation_stage = "copy.destination_check"
            if self.retry_handler.retry_on_temporary_error(
                self.fs.exists, destination_path
            ):
                logger.debug("Файл уже существует в назначении, перезаписываю: %s", destination_path)
                self.log_callback(f"🔄 Перезапись существующего файла: {filename}")
            else:
                logger.debug("Файл не существует в назначении, будет скопирован")
            
            logger.debug("Копирование файла размером %d байт: %s", source_size, filename)
            self.log_callback(f"Копирую файл: {source_path}")
            
            # Проверка отмены перед созданием директорий
            if self.cancel_token:
                self.cancel_token.raise_if_cancelled("Копирование отменено пользователем")
            
            # Создаем директорию назначения (с повторными попытками)
            dest_dir = self.fs.dirname(destination_path)
            operation_stage = "copy.create_directory"
            self.retry_handler.retry_on_temporary_error(
                self.fs.makedirs, dest_dir, exist_ok=True
            )
            logger.debug("Создана директория: %s", dest_dir)

            operation_stage = "copy.create_temporary_file"
            temp_path = self.retry_handler.retry_on_temporary_error(
                self.fs.create_temp_file,
                dest_dir,
                f".{filename}.",
                ".partial",
            )
            
            # Проверка отмены перед началом копирования
            if self.cancel_token:
                self.cancel_token.raise_if_cancelled("Копирование отменено пользователем")
            
            # Выбираем метод копирования на основе размера файла
            copy_method = get_copy_method(source_size)
            
            source_hash = None
            logger.debug(
                "copy_file: selected copy method (method=%s, source_size=%d)",
                copy_method.name if hasattr(copy_method, "name") else str(copy_method),
                source_size,
            )
            if copy_method == CopyMethod.SHUTIL:
                operation_stage = "copy.read_source"
                source_hash = self._copy_with_shutil(source_path, temp_path)
            elif copy_method == CopyMethod.BLOCK:
                operation_stage = "copy.read_source"
                source_hash = self._copy_with_blocks(
                    source_path,
                    temp_path,
                    source_size,
                    progress_callback,
                    base_copied_bytes,
                    total_bytes
                )

            operation_stage = "copy.source_validation"
            self._assert_source_unchanged(
                source_path,
                expected_size=source_size,
                expected_modified_ns=source_modified_ns,
            )

            operation_stage = "copy.temporary_size_validation"
            copied_size = self.retry_handler.retry_on_temporary_error(
                self.fs.getsize, temp_path
            )
            if copied_size != source_size:
                raise IOError(
                    "Размер временной копии не совпадает: "
                    f"источник={source_size}, копия={copied_size}"
                )

            if self.verification_mode == "full":
                operation_stage = "copy.hash_calculation"
                temp_hash = self._calculate_md5(temp_path)
                if temp_hash != source_hash:
                    operation_stage = "copy.hash_validation"
                    raise IOError(
                        f"Контрольная сумма временной копии не совпадает для файла: {filename}"
                    )

            if self.cancel_token:
                self.cancel_token.raise_if_cancelled("Копирование отменено пользователем")

            operation_stage = "copy.atomic_replace"
            self.retry_handler.retry_on_temporary_error(
                self.fs.replace, temp_path, destination_path
            )
            temp_path = None
            operation_stage = "copy.fsync_destination_directory"
            self.retry_handler.retry_on_temporary_error(
                self.fs.fsync_directory, dest_dir
            )
            operation_stage = "copy.final_size_validation"
            destination_size = self.retry_handler.retry_on_temporary_error(
                self.fs.getsize, destination_path
            )
            if destination_size != source_size:
                raise IOError(
                    "Размер конечной копии после атомарной замены не совпадает: "
                    f"источник={source_size}, копия={destination_size}"
                )

            if (
                self.verification_mode == "full"
                and source_hash is not None
                and self.verification_run_id is not None
            ):
                verification_result = CopyVerificationResult(
                    source_path=Path(os.path.realpath(os.path.abspath(source_path))),
                    destination_path=Path(os.path.realpath(os.path.abspath(destination_path))),
                    source_size=source_size,
                    destination_size=destination_size,
                    source_md5=source_hash,
                    destination_md5=temp_hash,
                    verification_mode=self.verification_mode,
                    verified_temporary_file=True,
                    temporary_file_synced_and_closed=True,
                    atomically_finalized=True,
                    run_id=self.verification_run_id,
                    operation_id=uuid.uuid4().hex,
                )

            if progress_callback:
                from utils import safe_add_bytes

                current_copied = safe_add_bytes(base_copied_bytes, source_size)
                percent = (
                    int(current_copied / total_bytes * 100)
                    if total_bytes > 0
                    else 0
                )
                progress_callback(percent, current_copied, total_bytes, 0.0, source_path)
            
            logger.debug("Файл скопирован в: %s", destination_path)
            self.log_callback(f"✓ Файл {filename} скопирован.")
            
            # Сохраняем хеш в HashStorage, если он доступен
            if source_hash and self.hash_storage:
                try:
                    modified_time = None
                    try:
                        modified_time = self.fs.getmtime(source_path)
                        modified_time = datetime.fromtimestamp(modified_time).isoformat()
                    except Exception:
                        pass
                    
                    logger.debug("Before hash_storage.set_hash() (source_path=%s)", source_path)
                    self.hash_storage.set_hash(
                        file_path=source_path,
                        hash_value=source_hash,
                        size=source_size,
                        modified_time=modified_time,
                        destination_path=destination_path
                    )
                    logger.debug("After hash_storage.set_hash() (source_path=%s)", source_path)
                except Exception as e:
                    logger.exception("Exception in hash_storage.set_hash()")
                    logger.warning("Не удалось сохранить хеш в HashStorage: %s", e)
            
            return CopyResult(
                success=True,
                copied_size=source_size,
                verification=verification_result,
            )
        except BackupCancelledError:
            logger.info("Copy cancelled (source_path=%s)", source_path)
            # Пробрасываем исключение отмены наверх без обработки
            raise
        except Exception as e:
            logger.exception("Exception in copy_file (source_path=%s)", source_path)
            issue_exc = e.original if isinstance(e, _CopyStageError) else e
            issue_stage = e.stage if isinstance(e, _CopyStageError) else operation_stage
            explicit_codes = {
                "copy.source_validation": OperationIssueCode.SOURCE_CHANGED,
                "copy.temporary_size_validation": OperationIssueCode.FILE_SIZE_MISMATCH,
                "copy.hash_calculation": OperationIssueCode.HASH_CALCULATION_FAILED,
                "copy.hash_validation": OperationIssueCode.HASH_MISMATCH,
                "copy.final_size_validation": OperationIssueCode.FILE_SIZE_MISMATCH,
            }
            explicit_code = explicit_codes.get(issue_stage)
            if isinstance(issue_exc, OSError) and issue_exc.errno is not None:
                explicit_code = None
            issue = create_operation_issue(
                issue_exc,
                stage=issue_stage,
                source_path=source_path,
                destination_path=destination_path,
                file_name=self.fs.basename(source_path),
                code=explicit_code,
            )
            error_msg = f"❌ {issue.message}: {issue.technical_message}"
            self.log_callback(error_msg)

            return CopyResult(success=False, copied_size=0, issue=issue)
        finally:
            if temp_path is not None:
                try:
                    if self.fs.exists(temp_path):
                        self.fs.remove(temp_path)
                except OSError as cleanup_error:
                    logger.warning(
                        "Не удалось удалить временный файл %s: %s",
                        temp_path,
                        cleanup_error,
                    )

    def _get_modified_ns(self, path: str) -> Optional[int]:
        """Возвращает mtime источника с максимальной точностью backend."""
        getmtime_ns = getattr(self.fs, "getmtime_ns", None)
        if getmtime_ns is not None:
            return int(
                self.retry_handler.retry_on_temporary_error(getmtime_ns, path)
            )
        modified = self.retry_handler.retry_on_temporary_error(
            self.fs.getmtime, path
        )
        return int(modified * 1_000_000_000)

    def _assert_source_unchanged(
        self,
        source_path: str,
        *,
        expected_size: int,
        expected_modified_ns: Optional[int],
    ) -> None:
        """Не допускает публикацию копии изменившегося во время чтения файла."""
        current_size = self.retry_handler.retry_on_temporary_error(
            self.fs.getsize, source_path
        )
        current_modified_ns = self._get_modified_ns(source_path)
        if current_size != expected_size or current_modified_ns != expected_modified_ns:
            raise IOError(
                "Исходный файл изменился во время копирования: "
                f"{source_path}"
            )

    def _calculate_md5(self, path: str) -> str:
        """Вычисляет MD5 временной копии с поддержкой отмены."""
        hash_md5 = hashlib.md5()
        with self.retry_handler.retry_on_temporary_error(self.fs.open, path, "rb") as file_object:
            while True:
                if self.cancel_token:
                    self.cancel_token.raise_if_cancelled(
                        "Проверка временной копии отменена пользователем"
                    )
                chunk = file_object.read(8 * 1024 * 1024)
                if not chunk:
                    return hash_md5.hexdigest()
                self.verification_read_bytes += len(chunk)
                hash_md5.update(chunk)


if __name__ == "__main__":
    """
    Точка входа для тестирования модуля file_copier.py
    """
    print("file_copier.py - модуль для копирования файлов")
    print("Этот модуль предназначен для использования в составе приложения Dублёр.")
    print("\nДля запуска основного приложения используйте:")
    print("  .venv/bin/python app.py")
    print("\nИли:")
    print("  ./run_in_venv.sh")
    print("\nМодуль успешно импортирован. Все зависимости доступны.")
