"""Виджет секции выбора назначения — новый UI"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from widgets import IntegratedDestinationWidget
from ui.ui_constants import UISpacing, UISizes, UIMargins
from ui_new.components.section_header import create_section_header


class DestinationSectionWidget(QWidget):
    """Виджет секции выбора назначения"""

    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app = app_instance

        layout = QVBoxLayout(self)
        layout.setSpacing(UISpacing.INTERNAL)
        layout.setContentsMargins(0, 0, 0, 0)

        header = create_section_header("Назначение")
        layout.addWidget(header)

        self.destination_widget = IntegratedDestinationWidget(
            self, app_instance=app_instance
        )
        self.destination_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self.destination_widget)

    def update_theme(self, theme: str):
        self.destination_widget.update_theme(theme)
