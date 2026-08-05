"""Виджет верхней части секции исходников: заголовок, drop zone, объём."""

from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt
from widgets import DropZone
from ui.ui_constants import UISpacing, UISizes, UIMargins
from ui_new.components.section_header import create_section_header
from paths import get_assets_animations_dir


def _resolve_media_folder_frames_dir() -> str:
    """Возвращает путь к папке PNG-кадров для блока источников."""
    base_dir = Path(get_assets_animations_dir())
    candidates = [
        base_dir / "media_folder_v2",
        base_dir / "media_folder",
    ]
    for frames_dir in candidates:
        if frames_dir.exists() and frames_dir.is_dir():
            return str(frames_dir)
    return ""


class SourcesHeaderAndDropWidget(QWidget):
    """Верх секции исходников: заголовок «Исходники», drop zone, метка объёма."""

    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app = app_instance

        layout = QVBoxLayout(self)
        layout.setSpacing(UISpacing.INTERNAL)
        layout.setContentsMargins(0, 0, 0, 0)

        header = create_section_header("Исходники")
        layout.addWidget(header)

        self.sources_drop = DropZone(
            self,
            "Перетащите сюда диски-источники<br>(папки или файлы) или кликните для выбора папки",
            is_destination=False,
            app_instance=app_instance,
            animation_frames_dir=_resolve_media_folder_frames_dir(),
        )
        self.sources_drop.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        self.sources_drop.setFixedHeight(UISizes.DROP_ZONE_HEIGHT)
        layout.addWidget(self.sources_drop)

        self.total_size_label = QLabel("")
        self.total_size_label.setObjectName("TotalSizeLabel")
        self.total_size_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.total_size_label.setStyleSheet(
            "color: #666; font-size: 12px; padding: 4px 0;"
        )
        self.total_size_label.setFixedHeight(UISizes.HEADER_HEIGHT)
        layout.addWidget(self.total_size_label)

        self.setMinimumHeight(
            UISizes.HEADER_HEIGHT
            + UISpacing.INTERNAL
            + UISizes.DROP_ZONE_HEIGHT
            + UISpacing.INTERNAL
            + UISizes.HEADER_HEIGHT
        )

    def update_theme(self, theme: str):
        self.sources_drop.update_theme(theme)
        self.sources_drop.setFixedHeight(UISizes.DROP_ZONE_HEIGHT)
