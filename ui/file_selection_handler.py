"""
Обработчик выбора и добавления файлов-источников.
Управляет логикой добавления источников через drag & drop и диалог выбора.
"""

import logging
from typing import Callable, List, Tuple, Optional
from backup_state_manager import BackupStateManager
from source_manager import SourceManager


logger = logging.getLogger(__name__)


class FileSelectionHandler:
    """Обрабатывает выбор и добавление файлов-источников"""
    
    def __init__(
        self,
        state_manager: BackupStateManager,
        source_manager: SourceManager
    ):
        """
        Инициализация обработчика
        
        :param state_manager: Менеджер состояния резервного копирования
        :param source_manager: Менеджер источников
        """
        self.state_manager = state_manager
        self.source_manager = source_manager
    
    def handle_drop_sources(
        self,
        paths: List[str],
        *,
        before_add: Optional[Callable[[str], bool]] = None,
    ) -> Tuple[List[str], List[str]]:
        """
        Обрабатывает drop источников (файлы или папки)
        
        :param paths: Список путей к источникам
        :return: Кортеж (список успешно добавленных путей, список дубликатов)
        """
        added_paths = []
        duplicate_paths = []
        
        for path in paths:
            # Валидация пути
            if not self.source_manager.validate_path(path):
                logger.warning("Путь не существует: %s", path)
                continue

            if before_add is not None and not before_add(path):
                continue
            
            # Проверка на дубликаты и добавление
            if self.state_manager.add_source_path(path):
                logger.debug("Добавлен источник через drag and drop: %s", path)
                added_paths.append(path)
            else:
                logger.debug("Источник уже добавлен: %s", path)
                duplicate_paths.append(path)
        
        return added_paths, duplicate_paths
    
    def handle_select_source(
        self,
        selected_path: str,
        *,
        before_add: Optional[Callable[[str], bool]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Обрабатывает выбор источника через диалог
        
        :param selected_path: Выбранный путь
        :return: Кортеж (True если источник был добавлен, путь дубликата или None)
        """
        # Валидация пути
        if not self.source_manager.validate_path(selected_path):
            logger.warning("Путь не существует: %s", selected_path)
            return False, None

        if before_add is not None and not before_add(selected_path):
            return False, None
        
        # Проверка на дубликаты и добавление
        if self.state_manager.add_source_path(selected_path):
            logger.debug("Добавлена папка-источник: %s", selected_path)
            return True, None
        else:
            logger.debug("Источник уже добавлен: %s", selected_path)
            return False, selected_path
