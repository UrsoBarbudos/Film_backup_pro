"""
Менеджер источников для резервного копирования.
Отвечает за работу с источниками: валидация, добавление, удаление, вычисление размеров.
"""

import logging
import os
from typing import Dict, Optional, TYPE_CHECKING, Callable
from utils import get_path_size
from engine import get_folder_predominant_category

if TYPE_CHECKING:
    from interfaces import IFileSystemInterface
    from engine_modules.scanning import ScanResult


logger = logging.getLogger(__name__)

class SourceManager:
    """Управляет источниками для резервного копирования"""
    
    def __init__(self, file_system: 'IFileSystemInterface'):
        """
        Инициализация менеджера источников

        :param file_system: Интерфейс ФС (обязателен, explicit DI).
        """
        self._file_system = file_system
        self._source_sizes: Dict[str, int] = {}  # Кэш размеров папок
        self._folder_categories: Dict[str, str] = {}  # Кэш категорий папок
        self._video_exts = {".mov", ".mp4", ".mxf", ".avi", ".r3d", ".mkv"}
        self._audio_exts = {".wav", ".mp3", ".aiff", ".flac", ".aac", ".m4a"}
        self._photo_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".dng", ".bmp", ".heic"}
        self._allowed_source_types = {"video", "audio", "photo", "data"}

    def validate_path(self, path: str, file_system: Optional['IFileSystemInterface'] = None) -> bool:
        """
        Валидирует путь источника
        
        :param path: Путь для проверки
        :param file_system: Интерфейс файловой системы (опционально, для тестирования)
        :return: True если путь валиден, False в противном случае
        """
        fs = file_system or self._file_system
        return fs.exists(path)
    
    def get_source_size(
        self,
        source_path: str,
        use_cache: bool = True,
        *,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> int:
        """
        Получает размер источника (файла или папки)
        
        :param source_path: Путь к источнику
        :param use_cache: Использовать кэш если доступен
        :return: Размер в байтах
        """
        
        
        if use_cache and source_path in self._source_sizes:
            
            return self._source_sizes[source_path]

        if should_cancel and should_cancel():
            return 0
        
        if not self.validate_path(source_path):
            
            return 0

        if should_cancel and should_cancel():
            return 0
        
        logger.info("Вычисление размера: %s", source_path)
        
        size_bytes = get_path_size(source_path, file_system=self._file_system, should_cancel=should_cancel)

        # Если отменили во время вычисления — не кэшируем результат (чтобы не «залипало» 0).
        if should_cancel and should_cancel():
            return 0

        self._source_sizes[source_path] = size_bytes
        return size_bytes
    
    def remove_source_size(self, source_path: str):
        """
        Удаляет размер источника из кэша
        
        :param source_path: Путь к источнику
        """
        if source_path in self._source_sizes:
            del self._source_sizes[source_path]
    
    def clear_cache(self):
        """Очищает кэш размеров и категорий"""
        self._source_sizes.clear()
        self._folder_categories.clear()
    
    def clear_source_from_cache(self, source_path: str):
        """Удаляет источник из кэша (алиас для совместимости)"""
        self.remove_source_size(source_path)
    
    def get_cached_size(self, source_path: str) -> Optional[int]:
        """
        Получает размер из кэша без вычисления
        
        :param source_path: Путь к источнику
        :return: Размер в байтах или None если не в кэше
        """
        return self._source_sizes.get(source_path)
    
    def get_total_sources_size(self) -> int:
        """
        Получает общий размер всех исходников из кэша
        
        :return: Общий размер в байтах
        """
        return sum(self._source_sizes.values())
    
    def get_folder_category(self, folder_path: str, use_cache: bool = True) -> str:
        """
        Получает преобладающую категорию папки
        
        :param folder_path: Путь к папке
        :param use_cache: Использовать кэш если доступен
        :return: Категория папки ('Video', 'Audio' или 'Photo')
        """
        if use_cache and folder_path in self._folder_categories:
            return self._folder_categories[folder_path]
        
        if not self.validate_path(folder_path):
            return 'Video'
        
        # Проверяем, что это директория
        if not self._file_system.isdir(folder_path):
            return 'Video'
        
        logger.info("Анализ категории папки: %s", folder_path)
        category = get_folder_predominant_category(folder_path, file_system=self._file_system)
        self._folder_categories[folder_path] = category
        return category

    def get_effective_source_type(self, source_path: str, *, override_type: Optional[str] = None) -> str:
        """
        Возвращает эффективный тип источника:
        1) пользовательский override, если валиден;
        2) автоопределение по папке/расширению.
        """
        override_norm = (override_type or "").strip().lower()
        if override_norm in self._allowed_source_types:
            return override_norm

        try:
            is_dir = bool(self._file_system.isdir(source_path))
        except Exception:
            is_dir = False
        if is_dir:
            try:
                category = (self.get_folder_category(source_path, use_cache=True) or "").strip().lower()
            except Exception:
                logger.exception("Не удалось определить категорию папки: %s", source_path)
                return "data"
            if category in self._allowed_source_types:
                return category
            return "data"

        _, ext = os.path.splitext(source_path)
        ext = ext.strip().lower()
        if ext in self._video_exts:
            return "video"
        if ext in self._audio_exts:
            return "audio"
        if ext in self._photo_exts:
            return "photo"
        return "data"
    
    def remove_folder_category(self, folder_path: str):
        """
        Удаляет категорию папки из кэша
        
        :param folder_path: Путь к папке
        """
        if folder_path in self._folder_categories:
            del self._folder_categories[folder_path]
    
    def update_from_scan_result(self, scan_result: 'ScanResult') -> None:
        """
        Обновляет кэш размеров из результата сканирования
        
        :param scan_result: Результат единого сканирования источников
        """
        for source_path, size in scan_result.source_sizes.items():
            self._source_sizes[source_path] = size
