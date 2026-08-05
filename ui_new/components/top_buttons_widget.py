"""Виджет верхних кнопок (Настройки, Очистить все) — новый UI"""

from PySide6.QtWidgets import QWidget, QHBoxLayout
from widgets import LinkButton
from ui.ui_constants import UIMargins, UISizes


class TopButtonsWidget(QWidget):
    """Виджет с верхними кнопками управления"""

    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app = app_instance

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.settings_button = LinkButton("Настройки")
        self.settings_button.setObjectName("SettingsLinkButton")
        self.settings_button.clicked.connect(self.app.open_settings)
        layout.addWidget(self.settings_button)

        layout.addStretch()

        self.clear_all_button = LinkButton("Очистить все")
        self.clear_all_button.setObjectName("SettingsLinkButton")
        self.clear_all_button.clicked.connect(self.app._clear_all_fields)
        layout.addWidget(self.clear_all_button)
        
        # Фиксированная высота для соответствия расчёту в main_window_content_height
        self.setFixedHeight(UISizes.TOP_BAR_HEIGHT)
