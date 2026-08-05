"""Диалог явного решения при добавлении ранее скопированного носителя."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QWidget

from compact_decision_dialog import CompactDecisionDialog, DecisionAction
from source_backup_marker import SourceBackupMarker
from utils import format_size


class PreviouslyBackedUpSourceDialogHandler:
    def confirm(self, marker: SourceBackupMarker, parent_widget: QWidget) -> bool:
        details = [("Дата", marker.verified_at.astimezone().strftime("%d.%m.%Y, %H:%M"))]
        if marker.destination_path:
            disk_name = os.path.basename(marker.destination_path.rstrip(os.sep))
            if disk_name:
                details.append(("Диск назначения", disk_name))
        if marker.source_file_count is not None:
            details.append(("Файлов", str(marker.source_file_count)))
        if marker.source_total_bytes is not None:
            details.append(("Общий объём", format_size(marker.source_total_bytes)))

        dialog = CompactDecisionDialog(
            parent_widget,
            title="Этот носитель уже копировался",
            text="На носителе найдена подтверждённая отметка Дублёра.",
            details=details,
            actions=(
                DecisionAction("cancel", "Не добавлять"),
                DecisionAction("add", "Добавить повторно"),
            ),
            reject_action="cancel",
        )
        dialog.exec()
        return dialog.selected_action == "add"
