"""
Контроллер процесса резервного копирования.
Управляет запуском процессов резервного копирования.
"""

import logging
from typing import Optional, Tuple

from PySide6.QtWidgets import QMessageBox, QWidget
from backup_launcher import BackupStarter
from backup_state_manager import BackupStateManager
from source_manager import SourceManager


logger = logging.getLogger(__name__)


class BackupProcessController:
    """Управляет запуском и продолжением процессов резервного копирования"""
    
    def __init__(
        self, 
        app_instance: QWidget,
        backup_starter: BackupStarter,
        state_manager: BackupStateManager,
        source_manager: SourceManager
    ):
        """
        Инициализация контроллера
        
        :param app_instance: Экземпляр главного окна приложения
        :param backup_starter: Экземпляр BackupStarter для запуска процессов
        :param state_manager: Экземпляр BackupStateManager для управления состоянием
        :param source_manager: Экземпляр SourceManager для работы с источниками
        """
        self.app = app_instance
        self.backup_starter = backup_starter
        self.state_manager = state_manager
        self.source_manager = source_manager
    
    def validate_backup_data(
        self, 
        destination_root: str, 
        source_drives: list
    ) -> Tuple[bool, Optional[str]]:
        """
        Валидация данных перед запуском
        
        :param destination_root: Корневая директория назначения
        :param source_drives: Список источников
        :return: Кортеж (is_valid, error_message)
        """
        if not destination_root or not source_drives:
            return False, "❌ Ошибка: Укажите назначение и источники перед запуском!"
        return True, None
    
    def prepare_ui_for_backup(self):
        """Подготовка UI (деактивация кнопок)"""
        self.app.start_button.setEnabled(False)
        self.app.start_button.setStyleSheet("background-color: #999;")
    
    def start_new_backup(
        self, 
        destination_root: str, 
        source_drives: list,
    ) -> None:
        """
        Запуск нового процесса резервного копирования
        
        :param destination_root: Корневая директория назначения
        :param source_drives: Список источников
        """
        logger.info("Запуск процесса резервного копирования...")
        logger.debug("Путь назначения: %s", destination_root)
        logger.debug("Источники: %s", source_drives)
        
        # Валидация
        is_valid, error_msg = self.validate_backup_data(destination_root, source_drives)
        if not is_valid:
            logger.error("%s", error_msg)
            self.app.log(error_msg)
            QMessageBox.critical(self.app, "Ошибка", error_msg)
            return
        
        # Подготовка UI
        self.prepare_ui_for_backup()
        
        # Запуск через BackupStarter
        self.backup_starter.launch_backup(
            destination_root=destination_root,
            source_drives=source_drives,
        )
