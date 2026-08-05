"""Общий компактный диалог для явного выбора одного действия."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class DecisionAction:
    key: str
    label: str


class CompactDecisionDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        text: str,
        actions: Iterable[DecisionAction],
        details: Iterable[tuple[str, str]] = (),
        checkbox_text: Optional[str] = None,
        reject_action: str,
    ) -> None:
        super().__init__(parent)
        self._selected_action = reject_action
        self.setWindowTitle(title)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        message = QLabel(text)
        message.setWordWrap(True)
        layout.addWidget(message)

        detail_lines = [f"{label}: {value}" for label, value in details if value]
        if detail_lines:
            details_label = QLabel("\n".join(detail_lines))
            details_label.setWordWrap(True)
            details_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(details_label)

        self.checkbox: Optional[QCheckBox] = None
        if checkbox_text:
            self.checkbox = QCheckBox(checkbox_text)
            layout.addWidget(self.checkbox)

        buttons = QHBoxLayout()
        buttons.addStretch()
        for action in actions:
            button = QPushButton(action.label)
            button.clicked.connect(lambda _checked=False, key=action.key: self._choose(key))
            buttons.addWidget(button)
        layout.addLayout(buttons)

    @property
    def selected_action(self) -> str:
        return self._selected_action

    def _choose(self, action: str) -> None:
        self._selected_action = action
        self.accept()
