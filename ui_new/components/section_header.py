"""Фабрика заголовков секций для унификации стиля."""

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from ui.ui_constants import UISizes


def create_section_header(text: str) -> QLabel:
    """
    Создаёт заголовок секции с единым стилем.
    
    Args:
        text: Текст заголовка
        
    Returns:
        QLabel с настроенным стилем заголовка секции
    """
    label = QLabel(text)
    label.setObjectName("SectionHeader")
    label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
    label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    label.setFixedHeight(UISizes.HEADER_HEIGHT)
    return label
