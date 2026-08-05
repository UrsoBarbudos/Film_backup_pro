"""
Диалог «О программе» — загрузка из .ui и подстановка версии/автора.
"""

import os
from typing import Optional

from PySide6.QtWidgets import QDialog, QLabel, QPushButton
from PySide6.QtUiTools import QUiLoader


def get_about_dialog_ui_path() -> str:
    """Путь к about_dialog.ui."""
    from ui_forms import get_ui_forms_dir
    return os.path.join(get_ui_forms_dir(), "about_dialog.ui")


class AboutDialog:
    """
    Обёртка над диалогом «О программе», загружаемым из about_dialog.ui.
    Версия и автор подставляются из кода.
    """

    def __init__(
        self,
        parent=None,
        version: str = "0.92",
        author: str = "@Urso_barbudos",
    ):
        self._parent = parent
        self._version = version
        self._author = author
        self._dialog: Optional[QDialog] = None

    def _load_dialog(self) -> QDialog:
        if self._dialog is not None:
            return self._dialog
        path = get_about_dialog_ui_path()
        if not os.path.isfile(path):
            raise FileNotFoundError(f"UI file not found: {path}")
        loader = QUiLoader()
        self._dialog = loader.load(path, self._parent)
        if self._dialog is None:
            raise RuntimeError(f"Failed to load UI: {path}")
        version_label = self._dialog.findChild(QLabel, "versionLabel")
        if version_label:
            version_label.setText(f"Версия: {self._version}")
        author_label = self._dialog.findChild(QLabel, "authorLabel")
        if author_label:
            author_label.setText(f"Автор: {self._author}")
        ok_btn = self._dialog.findChild(QPushButton, "okButton")
        if ok_btn:
            ok_btn.clicked.connect(self._dialog.accept)
        return self._dialog

    def exec(self) -> int:
        """Показывает диалог модально. Возвращает результат exec()."""
        dialog = self._load_dialog()
        return dialog.exec()
