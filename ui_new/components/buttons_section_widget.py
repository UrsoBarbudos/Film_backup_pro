"""Виджет секции кнопок — новый UI"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from ui.ui_constants import UISpacing, UISizes, UIMargins


class ButtonsSectionWidget(QWidget):
    """Виджет секции кнопок"""

    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app = app_instance

        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, UISpacing.BUTTONS, 0, 0)

        self.start_button = QPushButton("Начать копирование")
        self.start_button.setFixedHeight(UISizes.BUTTON_HEIGHT)
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.app.start_the_backup)
        layout.addWidget(self.start_button)
