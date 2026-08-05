from __future__ import annotations

from enum import Enum
from typing import Mapping


class BackupCompletionStatus(str, Enum):
    """Явный итог резервного копирования."""

    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"
    CANCELLED = "cancelled"


COMPLETION_MESSAGES = {
    BackupCompletionStatus.SUCCESS: "Копирование и проверка завершены успешно",
    BackupCompletionStatus.WARNING: "Копирование завершено с предупреждениями",
    BackupCompletionStatus.FAILED: "Резервное копирование завершено с ошибками",
    BackupCompletionStatus.CANCELLED: "Резервное копирование отменено",
}


def determine_completion_status(
    stats: Mapping[str, object],
    *,
    was_cancelled: bool = False,
) -> BackupCompletionStatus:
    """Возвращает SUCCESS только для полностью подтверждённой копии."""
    if was_cancelled:
        return BackupCompletionStatus.CANCELLED
    if int(stats.get("failed_files", 0) or 0) > 0:
        return BackupCompletionStatus.FAILED
    if int(stats.get("verification_failed_files", 0) or 0) > 0:
        return BackupCompletionStatus.FAILED
    if int(stats.get("unverified_files", 0) or 0) > 0:
        return BackupCompletionStatus.WARNING
    if stats.get("warnings"):
        return BackupCompletionStatus.WARNING
    return BackupCompletionStatus.SUCCESS
