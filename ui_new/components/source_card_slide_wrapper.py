"""Обёртка для карточки исходника."""

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Signal
from ui.ui_constants import UISizes

class SourceCardSlideWrapper(QWidget):
    """
    Контейнер для SourceItem: занимает место в layout, внутри — карточка.
    """

    slide_finished = Signal()

    def __init__(self, source_item: "QWidget", parent=None):
        super().__init__(parent)
        self._card = source_item
        self._card.setParent(self)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        # Фиксированная высота для всех карточек
        self.setFixedHeight(UISizes.SOURCE_ITEM_HEIGHT)
        self._card.setFixedHeight(UISizes.SOURCE_ITEM_HEIGHT)

    @property
    def source_item(self):
        """Карточка исходника внутри обёртки (для доступа из main_window)."""
        return self._card

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = event.size().width()
        h = event.size().height()
        self._card.setGeometry(0, 0, w, h)

    def start_slide_out(self) -> None:
        """Удаление карточки (без анимации, сразу эмитируем сигнал)."""
        # Сразу эмитируем сигнал завершения (без анимации)
        self.slide_finished.emit()
