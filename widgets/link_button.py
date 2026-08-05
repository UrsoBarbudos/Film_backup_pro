"""
Кнопка в виде текстовой ссылки с подчеркиванием
"""

from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt


class LinkButton(QPushButton):
    """Кнопка в виде текстовой ссылки с подчеркиванием"""
    
    def enterEvent(self, event):
        """Изменение курсора при наведении"""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Восстановление курсора при уходе"""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)
