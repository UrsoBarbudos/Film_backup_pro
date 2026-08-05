"""Виджет зоны карточек исходников с управляемой высотой."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QScrollBar, QSizePolicy, QHBoxLayout,
    QFrame, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve, Signal
from ui.ui_constants import UISizes, UIMargins, cards_area_height

ANIMATION_DURATION_MS = 300
SCROLL_ANIMATION_DURATION_MS = 250
RIGHT_SCROLLBAR_WIDTH = 8

SCROLLBAR_STYLE = """
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px 2px 0px 0px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.45);
        border-radius: 3px;
        min-height: 6px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(255, 255, 255, 0.6);
    }
    QScrollBar::handle:vertical:pressed {
        background: rgba(255, 255, 255, 0.8);
    }
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical { background: none; }
"""

class SourcesCardsWidget(QWidget):
    """Зона списка карточек исходников. Высота управляется через update_height(count)."""

    height_animation_finished = Signal()
    animated_height_changed = Signal(int)

    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app = app_instance
        self._animated_height = 0
        self._target_visible = False
        self._height_animation = QPropertyAnimation(self, b"animatedHeight")
        self._height_animation.setDuration(ANIMATION_DURATION_MS)
        self._height_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._height_animation.finished.connect(self._on_height_animation_finished)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)
        self._opacity_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._opacity_animation.setDuration(ANIMATION_DURATION_MS)
        self._opacity_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(0)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.scroll_area.setStyleSheet("border: none;")
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._internal_vbar = self.scroll_area.verticalScrollBar()
        self._internal_vbar.setStyleSheet(SCROLLBAR_STYLE)
        self._scroll_animation = QPropertyAnimation(self._internal_vbar, b"value", self)
        self._scroll_animation.setDuration(SCROLL_ANIMATION_DURATION_MS)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._scroll_animation.finished.connect(self._on_scroll_animation_finished)

        self._card_count = 0
        self._right_bar = QFrame()
        self._right_bar.setFixedWidth(RIGHT_SCROLLBAR_WIDTH)
        self._right_bar.setVisible(False)
        self._right_bar.setStyleSheet("background: transparent; border: none;")
        right_layout = QVBoxLayout(self._right_bar)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self._right_scrollbar.setStyleSheet(SCROLLBAR_STYLE)
        self._right_scrollbar.setFixedWidth(RIGHT_SCROLLBAR_WIDTH)
        right_layout.addWidget(self._right_scrollbar)
        self._right_scrollbar.valueChanged.connect(self._on_hover_scrollbar_value_changed)
        self._internal_vbar.valueChanged.connect(self._on_internal_vbar_value_changed)
        self._internal_vbar.rangeChanged.connect(self._sync_hover_scrollbar_range)

        self.sources_list_widget = QWidget()
        self.sources_list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        self.sources_list_layout = QVBoxLayout(self.sources_list_widget)
        self.sources_list_layout.setSpacing(UISizes.CARDS_LIST_SPACING)
        self.sources_list_layout.setContentsMargins(0, 0, 0, 0)
        self.sources_list_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.sources_list_layout.addStretch()

        self.scroll_area.setWidget(self.sources_list_widget)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area)
        self._right_bar.setParent(self)
        self._right_bar.raise_()

        # Начальная высота задается сразу без анимации, чтобы окно не "доезжало" при запуске.
        initial_h = cards_area_height(0)
        self._animated_height = initial_h
        self.setMinimumHeight(initial_h)
        self.setMaximumHeight(initial_h)
        self.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._right_bar.setGeometry(self.width() - RIGHT_SCROLLBAR_WIDTH, 0, RIGHT_SCROLLBAR_WIDTH, self.height())

    def _get_animated_height(self) -> int:
        return self._animated_height

    def _set_animated_height(self, value: int) -> None:
        """Setter для animatedHeight: обновляет высоту виджета и уведомляет layout."""
        if self._animated_height == value:
            return  # Избегаем лишних обновлений
        self._animated_height = value
        self.setMinimumHeight(value)
        self.setMaximumHeight(value)
        self.updateGeometry()  # Явно уведомляем parent layout об изменении размера
        self.animated_height_changed.emit(value)

    animatedHeight = Property(int, _get_animated_height, _set_animated_height)

    def _sync_hover_scrollbar_range(self, min_val: int, max_val: int) -> None:
        current_val = self._internal_vbar.value()
        self._right_scrollbar.blockSignals(True)
        self._right_scrollbar.setRange(min_val, max_val)
        self._right_scrollbar.setPageStep(self._internal_vbar.pageStep())
        self._right_scrollbar.setValue(current_val)
        self._right_scrollbar.blockSignals(False)

    def _on_hover_scrollbar_value_changed(self, value: int) -> None:
        self._internal_vbar.blockSignals(True)
        self._internal_vbar.setValue(value)
        self._internal_vbar.blockSignals(False)

    def _on_internal_vbar_value_changed(self, value: int) -> None:
        # DEBUG: Логируем изменения скролла (закомментировать после отладки - слишком много выводов)
        # print(f"[DEBUG SCROLL] _internal_vbar value changed: {value}")
        self._right_scrollbar.blockSignals(True)
        self._right_scrollbar.setValue(value)
        self._right_scrollbar.blockSignals(False)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self._card_count > UISizes.CARDS_VISIBLE_COUNT:
            self._sync_hover_scrollbar_range(
                self._internal_vbar.minimum(),
                self._internal_vbar.maximum(),
            )
            self._right_bar.setVisible(True)
    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._right_bar.setVisible(False)

    def scroll_to_bottom(self, animated: bool = True) -> None:
        """Прокрутить скролл вниз, чтобы показать последнюю добавленную карточку."""
        start_val = self._internal_vbar.value()
        end_val = self._internal_vbar.maximum()
        if end_val <= 0:
            return
        if not animated or end_val <= start_val:
            self._internal_vbar.setValue(end_val)
            self._sync_hover_scrollbar_range(
                self._internal_vbar.minimum(),
                self._internal_vbar.maximum(),
            )
            return
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(start_val)
        self._scroll_animation.setEndValue(end_val)
        self._scroll_animation.start()

    def _on_scroll_animation_finished(self) -> None:
        """Синхронизировать hover scrollbar после завершения анимации скролла."""
        self._sync_hover_scrollbar_range(
            self._internal_vbar.minimum(),
            self._internal_vbar.maximum(),
        )

    def _on_height_animation_finished(self) -> None:
        if not self._target_visible:
            self.setVisible(False)
            self._right_bar.setVisible(False)
            self._opacity_effect.setOpacity(0.0)
        self.height_animation_finished.emit()

    def update_height(self, card_count: int) -> None:
        """Задать высоту зоны: 0 -> 0, 1..6 -> N+0.5 карточек, 6+ -> фикс 6.5."""
        self._card_count = card_count
        target_h = cards_area_height(card_count)
        target_visible = card_count > 0
        self._target_visible = target_visible
        if target_visible and self.isHidden():
            self.setVisible(True)
        self._opacity_animation.stop()
        self._opacity_animation.setStartValue(self._opacity_effect.opacity())
        self._opacity_animation.setEndValue(1.0 if target_visible else 0.0)
        self._opacity_animation.start()
        current = self._animated_height
        if current == target_h:
            self.setMinimumHeight(target_h)
            self.setMaximumHeight(target_h)
            if not target_visible:
                self.setVisible(False)
                self._right_bar.setVisible(False)
                self._opacity_effect.setOpacity(0.0)
            else:
                self._opacity_effect.setOpacity(1.0)
            self.height_animation_finished.emit()
            return
        self._height_animation.stop()
        self._height_animation.setStartValue(current)
        self._height_animation.setEndValue(target_h)
        self._height_animation.start()
