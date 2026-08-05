"""
Модуль для отправки уведомлений о завершении резервного копирования.
Отвечает только за отправку уведомлений.
"""

import logging
from typing import Optional, Dict, Any, Callable
from notifications import NotificationManager
from interfaces import IConfig, IFileSystemInterface, ITelegramClient


logger = logging.getLogger(__name__)


class BackupNotifier:
    """Класс для отправки уведомлений о завершении копирования"""
    
    def __init__(
        self,
        log_callback: Optional[Callable[[str], None]] = None,
        *,
        config: Optional[IConfig] = None,
        file_system: Optional[IFileSystemInterface] = None,
        telegram_client: Optional[ITelegramClient] = None,
    ):
        """
        Инициализация нотификатора
        
        :param log_callback: Функция для логирования операций
        :param config: Экземпляр конфигурации (опционально)
        :param file_system: Интерфейс файловой системы (обязателен для отправки файла в Telegram)
        """
        self.log_callback = log_callback or (lambda msg: None)
        self.config = config
        self._file_system = file_system
        self._telegram_client = telegram_client
        self._notification_manager = None

        if self._file_system is None:
            raise ValueError("file_system must be provided to BackupNotifier (explicit DI).")
    
    def _get_notification_manager(self) -> NotificationManager:
        """
        Получает или создает менеджер уведомлений с настройками из конфига
        
        :return: NotificationManager
        """
        if self._notification_manager is None:
            try:
                # Загружаем настройки уведомлений
                if self.config is None:
                    raise ValueError("config must be provided to BackupNotifier (explicit DI).")
                settings = self.config.load()
                
                telegram_enabled = settings.get('telegram_enabled', False)
                telegram_bot_token = settings.get('telegram_bot_token', None)
                telegram_chat_id = settings.get('telegram_chat_id', None)
                macos_notifications_enabled = settings.get('macos_notifications_enabled', True)
                
                # Создаем менеджер уведомлений
                self._notification_manager = NotificationManager(
                    telegram_enabled=telegram_enabled,
                    telegram_bot_token=telegram_bot_token,
                    telegram_chat_id=telegram_chat_id,
                    macos_notifications_enabled=macos_notifications_enabled,
                    telegram_client=self._telegram_client,
                )
            except Exception as e:
                logger.warning("Ошибка при инициализации менеджера уведомлений: %s", e)
                # Создаем менеджер с настройками по умолчанию
                self._notification_manager = NotificationManager(
                    telegram_enabled=False,
                    macos_notifications_enabled=True,
                    telegram_client=self._telegram_client,
                )
        
        return self._notification_manager
    
    def send_notifications(
        self,
        stats: Dict[str, Any],
        md_log_path: Optional[str] = None
    ) -> None:
        """
        Отправляет уведомления о завершении копирования
        
        :param stats: Словарь со статистикой копирования
        :param md_log_path: Путь к MD лог-файлу (опционально, для Telegram)
        """
        try:
            notification_manager = self._get_notification_manager()
            
            # Отправляем Telegram уведомление, если включено и создан MD файл
            if notification_manager.telegram_enabled and md_log_path and self._file_system.exists(md_log_path):
                try:
                    notification_manager.send_telegram_notification(md_log_path, stats, self.log_callback)
                except Exception as e:
                    logger.warning("Ошибка при отправке Telegram уведомления: %s", e)
                    self.log_callback(f"⚠️ Не удалось отправить Telegram уведомление: {e}")
            
            # Отправляем системное уведомление macOS, если включено
            if notification_manager.macos_notifications_enabled:
                try:
                    notification_manager.send_macos_notification(stats, self.log_callback)
                except Exception as e:
                    logger.warning("Ошибка при отправке системного уведомления macOS: %s", e)
                    self.log_callback(f"⚠️ Не удалось отправить системное уведомление: {e}")
                    
        except Exception as e:
            logger.exception("Ошибка при отправке уведомлений: %s", e)
            # Не прерываем выполнение при ошибке уведомлений
