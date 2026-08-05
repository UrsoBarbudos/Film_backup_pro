"""
Модуль форм Qt Designer (.ui) и их обёрток.

Загрузка .ui в рантайме через PySide6.QtUiTools.QUiLoader.
"""

import os
import sys
from pathlib import Path


def get_ui_forms_dir() -> str:
    """
    Путь к директории с .ui файлами.

    В режиме разработки — каталог ui_forms рядом с этим файлом.
    В собранном приложении (frozen) — поддиректория в sys._MEIPASS.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "ui_forms")
    return str(Path(__file__).resolve().parent)
