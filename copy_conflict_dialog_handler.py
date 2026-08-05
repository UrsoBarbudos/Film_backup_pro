"""
Handler для диалога «Файл уже существует» при копировании.
Возвращает действие: Заменить / Пропустить / Оставить оба и опцию «Применять ко всем».
"""

import os
import threading
from typing import Tuple
from PySide6.QtWidgets import QWidget

from compact_decision_dialog import CompactDecisionDialog, DecisionAction


class CopyConflictDialogHandler:
    """Handler для диалога конфликта при копировании (файл уже существует)."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._result: Tuple[str, bool] = ("skip", False)

    def show_copy_conflict_dialog(
        self,
        source_path: str,
        destination_path: str,
        filename: str,
        parent_widget: QWidget,
    ) -> Tuple[str, bool]:
        """
        Показывает диалог «Файл уже существует» и возвращает (action, apply_to_all).

        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param filename: Имя файла для отображения
        :param parent_widget: Родительский виджет для диалога
        :return: ('replace' | 'skip' | 'keep_both', apply_to_all: bool)
        """
        display_name = filename or (os.path.basename(source_path) if source_path else os.path.basename(destination_path))

        dialog = CompactDecisionDialog(
            parent_widget,
            title="Файл уже существует",
            text=f"Файл «{display_name}» уже существует в назначении.\nВыберите действие:",
            actions=(
                DecisionAction("replace", "Заменить"),
                DecisionAction("skip", "Пропустить"),
                DecisionAction("keep_both", "Оставить оба"),
            ),
            checkbox_text="Применять ко всем",
            reject_action="skip",
        )
        dialog.exec()
        apply_to_all = bool(dialog.checkbox and dialog.checkbox.isChecked())
        return dialog.selected_action, apply_to_all

    def set_copy_conflict_result(self, action: str, apply_to_all: bool) -> None:
        """Устанавливает результат для разблокировки потока копирования."""
        self._result = (action, apply_to_all)
        self._event.set()

    def get_copy_conflict_action(
        self,
        source_path: str,
        destination_path: str,
        filename: str,
        timeout: float = 300.0,
    ) -> Tuple[str, bool]:
        """
        Блокирует поток копирования до ответа пользователя (до вызова set_copy_conflict_result из UI).

        :return: (action, apply_to_all)
        """
        self._event.clear()
        self._result = ("skip", False)
        if self._event.wait(timeout):
            return self._result
        return ("skip", False)
