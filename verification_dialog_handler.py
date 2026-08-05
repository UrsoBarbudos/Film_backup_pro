"""
Handler для управления диалогами проверки файлов
Отвечает за показ диалогов и управление результатами проверки
"""

import os
import threading
from typing import Optional
from PySide6.QtWidgets import QMessageBox, QWidget


class VerificationDialogHandler:
    """Handler для управления диалогами проверки файлов"""
    
    def __init__(self):
        """Инициализация Handler"""
        # Словарь для хранения результатов диалогов проверки
        # Ключ: (source_path, destination_path), значение: 'recopy', 'skip', или 'cancel'
        self._verification_actions = {}
        
        # Event для ожидания ответа пользователя
        self._verification_event = threading.Event()
        self._verification_result: Optional[str] = None
    
    def show_verification_dialog(self, source_path: str, destination_path: str, 
                                error_message: str, parent_widget: QWidget) -> str:
        """
        Показывает диалог проверки файла и возвращает действие пользователя
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param error_message: Сообщение об ошибке
        :param parent_widget: Родительский виджет для диалога
        :return: 'recopy', 'skip', или 'cancel'
        """
        filename = os.path.basename(source_path) if source_path else os.path.basename(destination_path)
        
        # Создаем диалог с выбором действия
        msg_box = QMessageBox(parent_widget)
        msg_box.setWindowTitle("Ошибка проверки файла")
        msg_box.setText(f"Ошибка проверки файла:\n{filename}")
        msg_box.setInformativeText(f"{error_message}\n\nЧто вы хотите сделать?")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        
        # Добавляем кнопки
        recopy_btn = msg_box.addButton("Перекопировать", QMessageBox.ButtonRole.AcceptRole)
        skip_btn = msg_box.addButton("Пропустить", QMessageBox.ButtonRole.RejectRole)
        cancel_btn = msg_box.addButton("Отменить", QMessageBox.ButtonRole.DestructiveRole)
        
        # Показываем диалог (блокирующий)
        msg_box.exec()
        
        # Определяем действие пользователя
        clicked_button = msg_box.clickedButton()
        if clicked_button == recopy_btn:
            action = 'recopy'
        elif clicked_button == skip_btn:
            action = 'skip'
        elif clicked_button == cancel_btn:
            action = 'cancel'
        else:
            # По умолчанию отменяем, если кнопка не распознана
            action = 'cancel'
        
        # Сохраняем результат
        key = (source_path, destination_path)
        self._verification_actions[key] = action
        
        return action
    
    def get_verification_action(self, source_path: str, destination_path: str, 
                               timeout: float = 300.0) -> str:
        """
        Получает действие пользователя для ошибки проверки
        Использует кеш, если действие уже было запрошено для этого файла
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param timeout: Таймаут ожидания в секундах (не используется, так как диалог блокирующий)
        :return: 'recopy', 'skip', или 'cancel'
        """
        key = (source_path, destination_path)
        
        # Проверяем, есть ли уже сохраненный ответ
        if key in self._verification_actions:
            return self._verification_actions[key]
        
        # Если ответа нет, возвращаем 'skip' по умолчанию
        # (реальный диалог должен быть показан через show_verification_dialog)
        return 'skip'
    
    def clear_cache(self):
        """Очищает кеш результатов диалогов"""
        self._verification_actions.clear()
    
    def set_verification_action(self, source_path: str, destination_path: str, action: str):
        """
        Устанавливает действие для конкретного файла (для использования с сигналами Qt)
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param action: Действие ('recopy', 'skip', или 'cancel')
        """
        key = (source_path, destination_path)
        self._verification_actions[key] = action
        self._verification_result = action
        self._verification_event.set()
    
    def wait_for_action(self, timeout: float = 300.0) -> Optional[str]:
        """
        Ждет установки действия через set_verification_action (для использования с сигналами Qt)
        
        :param timeout: Таймаут ожидания в секундах
        :return: Действие или None при таймауте
        """
        if self._verification_event.wait(timeout):
            return self._verification_result
        else:
            return 'cancel'

    def prepare_for_action(self) -> None:
        """Сбрасывает ожидание до отправки Qt-сигнала, исключая гонку."""
        self._verification_event.clear()
        self._verification_result = None
