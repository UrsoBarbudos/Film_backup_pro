"""
Виджет для отображения источника в списке
"""

import logging
import os
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, Signal, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor
from .elided_label import ElidedLabel
from .link_button import LinkButton
from utils import format_size, get_path_size

logger = logging.getLogger(__name__)

HOVER_ANIMATION_DURATION_MS = 150


class _TypeComboBox(QComboBox):
    """QComboBox, при закрытии popup вызывающий callback (восстановление UI при выборе того же пункта)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on_hide_popup: Optional[Callable[[], None]] = None

    def set_on_hide_popup(self, callback: Optional[Callable[[], None]]) -> None:
        self._on_hide_popup = callback

    def hidePopup(self) -> None:
        super().hidePopup()
        if self._on_hide_popup:
            self._on_hide_popup()


class SourceItem(QFrame):
    """Виджет для отображения источника в списке"""

    remove_requested = Signal(str)
    source_type_changed = Signal(str, str)
    ALLOWED_SOURCE_TYPES = ("video", "audio", "photo", "data")

    def __init__(
        self,
        source_path: str,
        app_instance,
        parent=None,
        size_bytes=None,
        source_type: Optional[str] = None,
    ):
        super().__init__(parent)
        self.source_path = source_path
        self.app_instance = app_instance
        self.theme = app_instance.theme if app_instance else 'light'
        self._current_source_type = self._normalize_source_type(source_type) or "data"
        
        self._bg_color = QColor(self._get_normal_bg_color())
        self._hover_animation = QPropertyAnimation(self, b"bgColor")
        self._hover_animation.setDuration(HOVER_ANIMATION_DURATION_MS)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.setFrameStyle(QFrame.Shape.Box)
        self.setObjectName("SourceItem")
        
        # Расширяемая ширина с минимальной шириной, фиксированная высота
        self.setMinimumWidth(300)  # Минимальная ширина для консистентности
        self.setFixedHeight(48)   # Высота остается фиксированной
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.type_widget = QWidget(self)
        self.type_widget.setObjectName("SourceItemTypeWidget")
        type_layout = QVBoxLayout(self.type_widget)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(0)

        self.type_tag_button = QPushButton(self._current_source_type.upper(), self)
        self.type_tag_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.type_tag_button.setFixedHeight(28)
        self.type_tag_button.setFixedWidth(80)
        self.type_tag_button.clicked.connect(self._show_type_dropdown)
        type_layout.addWidget(self.type_tag_button)

        self.type_combo = _TypeComboBox(self)
        self.type_combo.addItems([t.upper() for t in self.ALLOWED_SOURCE_TYPES])
        self.type_combo.setCurrentText(self._current_source_type.upper())
        self.type_combo.currentTextChanged.connect(self._on_type_selected)
        self.type_combo.activated.connect(self._on_type_activated)
        self.type_combo.set_on_hide_popup(self._restore_type_ui_only)
        self.type_combo.hide()
        self.type_combo.setFixedHeight(28)
        self.type_combo.setFixedWidth(92)
        type_layout.addWidget(self.type_combo)

        self.type_widget.setFixedWidth(80)
        layout.addWidget(self.type_widget)

        info_widget = QWidget()
        info_widget.setObjectName("SourceItemInfoWidget")
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        clean_path = source_path.rstrip('/') if source_path != '/' else source_path
        volume_name = os.path.basename(clean_path) or source_path
        self.volume_title_label = QLabel("Volume")
        self.volume_title_label.setFont(QFont("Arial", 10))
        self.volume_value_label = ElidedLabel(volume_name)
        self.volume_value_label.setObjectName("SourceItemVolumeValue")
        self.volume_value_label.setFont(QFont("Arial", 12))
        self.volume_value_label.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.volume_value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_layout.addWidget(self.volume_value_label)

        if size_bytes is not None:
            size_str = format_size(size_bytes)
        else:
            size_str = format_size(get_path_size(source_path))
        self.size_title_label = QLabel("Size")
        self.size_title_label.setFont(QFont("Arial", 10))
        self.size_value_label = QLabel(size_str)
        self.size_value_label.setObjectName("SourceItemSizeValue")
        self.size_value_label.setFont(QFont("Arial", 11))
        info_layout.addWidget(self.size_value_label)

        self.type_title_label = QLabel("Type")
        self.type_title_label.setFont(QFont("Arial", 10))

        info_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(info_widget, 1)

        # Aliases для обратной совместимости с текущими вызовами
        self.name_label = self.volume_value_label
        self.size_label = self.size_value_label

        # Кнопка удаления в стиле ссылки (как «Настройки»)
        self.remove_btn = LinkButton("Удалить", self)
        self.remove_btn.setObjectName("SettingsLinkButton")
        self.remove_btn.setFixedHeight(28)
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        layout.addWidget(self.remove_btn)

        # Применяем стили в зависимости от темы
        self._apply_theme_styles()

    def _get_normal_bg_color(self) -> str:
        return "#3b3b3b" if self.theme == 'dark' else "white"

    def _get_hover_bg_color(self) -> str:
        return "#444444" if self.theme == 'dark' else "#f0f9f5"

    def _get_bg_color(self) -> QColor:
        return self._bg_color

    def _set_bg_color(self, color: QColor) -> None:
        self._bg_color = color
        self._apply_background_only()

    bgColor = Property(QColor, _get_bg_color, _set_bg_color)

    def _apply_background_only(self) -> None:
        """Обновляет только фон карточки для плавной hover анимации."""
        border_color = "#2FA572"
        bg = self._bg_color.name()
        self.setStyleSheet(f"""
            QFrame#SourceItem {{
                border: 1px solid {border_color};
                border-radius: 4px;
                background-color: {bg};
            }}
            QWidget#SourceItemInfoWidget {{
                background-color: transparent;
            }}
            QWidget#SourceItemTypeWidget {{
                background-color: {bg};
                border: none;
            }}
        """)

    def _apply_theme_styles(self):
        """Применяет стили в зависимости от темы"""
        if hasattr(self, '_bg_color'):
            self._bg_color = QColor(self._get_normal_bg_color())
        
        if self.theme == 'dark':
            border_color = "#2FA572"  # Граница для добавленных источников
            bg_color = "#3b3b3b"
            name_color = "white"
            size_color = "#aaa"
            format_color = "white"
            hover_bg = "#3b3b3b"
        else:
            border_color = "#2FA572"  # Зеленая граница для добавленных источников
            bg_color = "white"
            name_color = "black"
            size_color = "#999"  # Светло-серый для размера
            format_color = "black"
            hover_bg = "#f5f5f5"
        
        
        
        self.setStyleSheet(f"""
            QFrame#SourceItem {{
                border: 1px solid {border_color};
                border-radius: 4px;
                background-color: {bg_color};
            }}
            QWidget#SourceItemInfoWidget {{
                background-color: transparent;
            }}
            QWidget#SourceItemTypeWidget {{
                background-color: {bg_color};
                border: none;
            }}
        """)
        
        self.volume_value_label.setStyleSheet(f"color: {name_color}; background-color: transparent;")
        self.size_value_label.setStyleSheet(f"color: {name_color}; background-color: transparent;")
        self.volume_title_label.setStyleSheet(f"color: {size_color}; background-color: transparent;")
        self.size_title_label.setStyleSheet(f"color: {size_color}; background-color: transparent;")
        self.type_title_label.setStyleSheet(f"color: {size_color}; background-color: transparent;")

        self.type_tag_button.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: 12px;
                background-color: transparent;
                color: {format_color};
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background-color: transparent;
                color: {format_color};
            }}
            QPushButton:focus {{
                border: none;
                outline: none;
                background-color: transparent;
                color: {format_color};
            }}
            QPushButton:pressed {{
                border: none;
                outline: none;
                background-color: transparent;
                color: {format_color};
            }}
        """)

        # Стиль кнопки «удалить» как у кнопки «Настройки» (ссылка с подчёркиванием)
        remove_btn_color = "#666" if self.theme == 'light' else "#aaa"
        remove_btn_hover_color = "#999" if self.theme == 'light' else "#ccc"
        self.remove_btn.setStyleSheet(f"""
            QPushButton#SettingsLinkButton {{
                background-color: transparent;
                color: {remove_btn_color};
                border: none;
                border-radius: 0px;
                padding: 2px 2px 2px 0;
                text-decoration: underline;
                font-size: 12px;
            }}
            QPushButton#SettingsLinkButton:hover {{
                background-color: transparent;
                color: {remove_btn_hover_color};
            }}
        """)

        self.type_combo.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {border_color};
                border-radius: 8px;
                background-color: {bg_color};
                color: {name_color};
                padding: 0 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {bg_color};
                color: {name_color};
                selection-background-color: {hover_bg};
            }}
        """)

    def update_size(self, size_bytes: int):
        """Обновляет отображаемый размер источника"""
        # Защита от отрицательных значений
        if size_bytes < 0:
            logger.warning(
                "update_size получил отрицательное значение для %s: %s",
                self.source_path,
                size_bytes,
            )
            size_bytes = 0

        from utils import format_size
        size_str = format_size(size_bytes)
        self.size_label.setText(size_str)

    def update_source_type(self, source_type: str) -> None:
        """Обновляет отображаемый тип источника без эмита сигнала изменения."""
        normalized = self._normalize_source_type(source_type)
        if normalized is None:
            return
        self._current_source_type = normalized
        self.type_tag_button.setText(normalized.upper())
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentText(normalized.upper())
        self.type_combo.blockSignals(False)

    def _on_remove_clicked(self) -> None:
        self.remove_requested.emit(self.source_path)

    def _restore_type_ui_only(self) -> None:
        """Восстанавливает вид (кнопка тега видна, комбобокс скрыт) без смены типа и без emit. Вызывается при закрытии popup без выбора другого пункта."""
        self.type_combo.hide()
        self.type_tag_button.show()

    def _show_type_dropdown(self) -> None:
        self.type_tag_button.hide()
        self.type_combo.show()
        self.type_combo.setFocus()
        self.type_combo.showPopup()

    def _on_type_selected(self, selected_type: str) -> None:
        normalized = self._normalize_source_type(selected_type)
        if normalized is None:
            return
        self._current_source_type = normalized
        self.type_tag_button.setText(normalized.upper())
        self.type_combo.hide()
        self.type_tag_button.show()
        self.source_type_changed.emit(self.source_path, normalized)

    def _on_type_activated(self, _index: int) -> None:
        """
        QComboBox.currentTextChanged может не сработать при выборе того же значения.
        Здесь принудительно синхронизируем UI в любом случае.
        """
        self._on_type_selected(self.type_combo.currentText())

    def _normalize_source_type(self, source_type: Optional[str]) -> Optional[str]:
        if source_type is None:
            return None
        normalized = source_type.strip().lower()
        if normalized in self.ALLOWED_SOURCE_TYPES:
            return normalized
        return None

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._bg_color)
        self._hover_animation.setEndValue(QColor(self._get_hover_bg_color()))
        self._hover_animation.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._bg_color)
        self._hover_animation.setEndValue(QColor(self._get_normal_bg_color()))
        self._hover_animation.start()

    def showEvent(self, event):
        super().showEvent(event)
