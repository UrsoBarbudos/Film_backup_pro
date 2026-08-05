"""
Виджет QLabel с поддержкой обрезки текста
"""

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QFontMetrics


class ElidedLabel(QLabel):
    """QLabel с поддержкой обрезки текста"""
    
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._elide_mode = Qt.TextElideMode.ElideMiddle
        self._full_text = text  # Сохраняем полный текст
    
    def setText(self, text):
        """Переопределяем setText для сохранения полного текста"""
        self._full_text = text
        super().setText(text)
        self.update()
    
    def setTextElideMode(self, mode):
        """Устанавливает режим обрезки текста"""
        self._elide_mode = mode
        self.update()
    
    def resizeEvent(self, event):
        """Обрабатываем изменение размера для обновления обрезки"""
        super().resizeEvent(event)
        self.update()
    
    def paintEvent(self, event):
        """Переопределяем отрисовку для поддержки обрезки текста"""
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        # Используем сохраненный полный текст для обрезки
        available_width = self.width() - 2  # Небольшой отступ от краев
        elided_text = metrics.elidedText(self._full_text, self._elide_mode, available_width)
        painter.drawText(self.rect(), self.alignment(), elided_text)
