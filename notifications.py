"""
Модуль для отправки уведомлений о завершении копирования
Поддерживает Telegram Bot и системные уведомления macOS
"""

import os
import logging
import subprocess
from typing import Optional, Dict, Any, Tuple

from integrations import TelegramClient
from interfaces import ITelegramClient

logger = logging.getLogger(__name__)


class NotificationManager:
    """Класс для управления уведомлениями о завершении копирования"""
    
    def __init__(
        self,
        telegram_enabled: bool = False,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        macos_notifications_enabled: bool = True,
        telegram_client: Optional[ITelegramClient] = None,
    ):
        """
        Инициализация менеджера уведомлений
        
        :param telegram_enabled: Включены ли уведомления Telegram
        :param telegram_bot_token: Токен Telegram бота
        :param telegram_chat_id: ID чата для отправки сообщений
        :param macos_notifications_enabled: Включены ли системные уведомления macOS
        """
        self.telegram_enabled = telegram_enabled
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.macos_notifications_enabled = macos_notifications_enabled
        self.telegram_client = telegram_client or TelegramClient()
    
    def send_telegram_notification(self, md_file_path: str, stats: Optional[Dict[str, Any]] = None,
                                   log_callback=None) -> bool:
        """
        Отправляет уведомление в Telegram с содержимым MD файла
        
        :param md_file_path: Путь к MD файлу с логом копирования
        :param stats: Словарь со статистикой копирования (опционально)
        :param log_callback: Функция для логирования (опционально)
        :return: True если уведомление отправлено успешно, False в противном случае
        """
        if not self.telegram_enabled:
            if log_callback:
                log_callback("Telegram уведомления отключены")
            return False
        
        if not self.telegram_bot_token or not self.telegram_chat_id:
            error_msg = "Telegram токен или Chat ID не указаны"
            if log_callback:
                log_callback(f"⚠️ {error_msg}")
            logger.warning("%s", error_msg)
            return False

        if not os.path.exists(md_file_path):
            error_msg = f"MD файл не найден: {md_file_path}"
            if log_callback:
                log_callback(f"❌ {error_msg}")
            logger.error("%s", error_msg)
            return False

        try:
            with open(md_file_path, "r", encoding="utf-8") as file_obj:
                md_content = file_obj.read()
        except OSError as exc:
            if log_callback:
                log_callback(f"❌ Не удалось прочитать MD лог: {exc}")
            logger.exception("Не удалось прочитать MD лог %s", md_file_path)
            return False

        message_parts = []
        if stats:
            successful_files = stats.get("successful_files", 0)
            total_files = stats.get("total_files", 0)
            failed_files = stats.get("failed_files", 0)
            completion_status = stats.get("completion_status", "failed")
            status_emoji = "✅" if completion_status == "success" else "⚠️"
            message_parts.append(
                f"{status_emoji} *Копирование завершено*\n"
                f"Файлов: {successful_files}/{total_files}"
            )
            if failed_files > 0:
                message_parts.append(f"Ошибок: {failed_files}")
            message_parts.append("")

        message_parts.extend(("```", md_content, "```"))
        full_message = "\n".join(message_parts)
        if len(full_message) > 4096:
            max_md_length = 4096 - len("\n".join(message_parts[:-2])) - 10
            truncated_md = (
                md_content[:max_md_length]
                + "\n\n... (файл обрезан, полная версия сохранена локально)"
            )
            full_message = "\n".join(message_parts[:-2]) + "\n```\n" + truncated_md + "\n```"

        result = self.telegram_client.send_message(
            self.telegram_bot_token,
            self.telegram_chat_id,
            full_message,
            parse_mode="Markdown",
        )
        if result.success:
            if log_callback:
                log_callback("✅ Уведомление отправлено в Telegram")
            return True
        if log_callback:
            log_callback(f"❌ {result.message}")
        logger.warning("Telegram notification failed: %s (%s)", result.message, result.error_code)
        return False
    
    def send_simple_notification(self, title: str, message: str, log_callback=None) -> bool:
        """
        Отправляет простое системное уведомление macOS через Notification Center
        
        :param title: Заголовок уведомления
        :param message: Текст сообщения уведомления
        :param log_callback: Функция для логирования (опционально)
        :return: True если уведомление отправлено успешно, False в противном случае
        """
        if not self.macos_notifications_enabled:
            if log_callback:
                log_callback("Системные уведомления macOS отключены")
            return False
        
        try:
            # Используем osascript для отправки системного уведомления macOS
            # Экранируем специальные символы для AppleScript
            title_escaped = title.replace('\\', '\\\\').replace('"', '\\"')
            message_escaped = message.replace('\\', '\\\\').replace('"', '\\"')
            
            applescript = f'''
                display notification "{message_escaped}" with title "{title_escaped}"
            '''
            
            # Выполняем AppleScript через osascript
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                if log_callback:
                    log_callback(f"✅ Системное уведомление отправлено: {title}")
                return True
            else:
                error_msg = f"Ошибка при отправке системного уведомления: {result.stderr}"
                if log_callback:
                    log_callback(f"⚠️ {error_msg}")
                print(f"WARNING: {error_msg}", flush=True)
                return False
                
        except subprocess.TimeoutExpired:
            error_msg = "Таймаут при отправке системного уведомления"
            if log_callback:
                log_callback(f"⚠️ {error_msg}")
            print(f"WARNING: {error_msg}", flush=True)
            return False
        except Exception as e:
            error_msg = f"Неожиданная ошибка при отправке системного уведомления: {e}"
            if log_callback:
                log_callback(f"⚠️ {error_msg}")
            print(f"WARNING: {error_msg}", flush=True)
            import traceback
            print(f"TRACEBACK: {traceback.format_exc()}", flush=True)
            return False
    
    def send_macos_notification(self, stats: Optional[Dict[str, Any]] = None,
                                log_callback=None) -> bool:
        """
        Отправляет системное уведомление macOS через Notification Center
        
        :param stats: Словарь со статистикой копирования (опционально)
        :param log_callback: Функция для логирования (опционально)
        :return: True если уведомление отправлено успешно, False в противном случае
        """
        if not self.macos_notifications_enabled:
            if log_callback:
                log_callback("Системные уведомления macOS отключены")
            return False
        
        try:
            # Формируем текст уведомления
            if stats:
                successful_files = stats.get('successful_files', 0)
                total_files = stats.get('total_files', 0)
                failed_files = stats.get('failed_files', 0)
                
                completion_status = stats.get("completion_status", "failed")
                if completion_status == "success":
                    title = "✅ Копирование завершено"
                    message = f"Файлов скопировано: {successful_files}/{total_files}"
                elif completion_status == "warning":
                    title = "⚠️ Резервная копия требует внимания"
                    message = f"Успешно: {successful_files}/{total_files}"
                else:
                    title = "❌ Резервное копирование завершено с ошибками"
                    message = f"Успешно: {successful_files}/{total_files}, Ошибок: {failed_files}"
            else:
                title = "Копирование завершено"
                message = "Резервное копирование завершено"
            
            # Используем send_simple_notification для отправки
            return self.send_simple_notification(title, message, log_callback)
                
        except Exception as e:
            error_msg = f"Неожиданная ошибка при отправке системного уведомления: {e}"
            if log_callback:
                log_callback(f"⚠️ {error_msg}")
            print(f"WARNING: {error_msg}", flush=True)
            import traceback
            print(f"TRACEBACK: {traceback.format_exc()}", flush=True)
            return False
    
    def test_telegram_connection(self) -> Tuple[bool, str]:
        """
        Проверяет подключение к Telegram Bot API
        
        :return: Кортеж (успех: bool, сообщение: str)
        """
        if not self.telegram_enabled:
            return False, "Telegram уведомления отключены"
        
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return False, "Telegram токен или Chat ID не указаны"
        
        result = self.telegram_client.test_connection(
            self.telegram_bot_token,
            self.telegram_chat_id,
        )
        return result.success, result.message
