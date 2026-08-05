from __future__ import annotations

import errno
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class OperationIssueCode(str, Enum):
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_UNREADABLE = "SOURCE_UNREADABLE"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    DESTINATION_UNAVAILABLE = "DESTINATION_UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NO_SPACE_LEFT = "NO_SPACE_LEFT"
    READ_FAILED = "READ_FAILED"
    WRITE_FAILED = "WRITE_FAILED"
    FSYNC_FAILED = "FSYNC_FAILED"
    ATOMIC_REPLACE_FAILED = "ATOMIC_REPLACE_FAILED"
    FILE_SIZE_MISMATCH = "FILE_SIZE_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    HASH_CALCULATION_FAILED = "HASH_CALCULATION_FAILED"
    SCAN_FAILED = "SCAN_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    REPORT_WRITE_FAILED = "REPORT_WRITE_FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass(frozen=True, slots=True)
class OperationIssue:
    stage: str
    code: str
    message: str
    source_path: Optional[str] = None
    destination_path: Optional[str] = None
    file_name: Optional[str] = None
    technical_message: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now().astimezone())
    fatal: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


_STAGE_MESSAGES: dict[str, str] = {
    "scanning": "Не удалось просканировать источник",
    "planning": "Не удалось подготовить файл к копированию",
    "copy.source_metadata": "Не удалось прочитать сведения об исходном файле",
    "copy.destination_check": "Не удалось проверить файл назначения",
    "copy.create_directory": "Не удалось создать папку назначения",
    "copy.create_temporary_file": "Не удалось создать временный файл",
    "copy.read_source": "Не удалось прочитать исходный файл",
    "copy.write_temporary_file": "Не удалось записать временный файл",
    "copy.fsync_temporary_file": "Не удалось синхронизировать временный файл с диском",
    "copy.source_validation": "Исходный файл изменился во время копирования",
    "copy.temporary_size_validation": "Размер временной копии не совпадает с исходным файлом",
    "copy.hash_calculation": "Не удалось рассчитать контрольную сумму",
    "copy.hash_validation": "Контрольная сумма временной копии не совпадает",
    "copy.atomic_replace": "Не удалось атомарно опубликовать скопированный файл",
    "copy.fsync_destination_directory": (
        "Файл опубликован, но не удалось синхронизировать папку назначения"
    ),
    "copy.final_size_validation": "Опубликованный файл имеет неожиданный размер",
    "verification": "Не удалось проверить скопированный файл",
    "verification.size": "Не удалось проверить размеры файлов",
    "verification.sample_hash": "Не удалось рассчитать контрольную выборку файла",
    "verification.hash": "Не удалось рассчитать контрольную сумму файла",
    "finalization": "Не удалось завершить резервное копирование",
    "report.write": "Не удалось сохранить Markdown-отчёт",
    "report.fsync": "Не удалось синхронизировать Markdown-отчёт с диском",
    "report.replace": "Не удалось атомарно опубликовать Markdown-отчёт",
}


def _default_code(exc: BaseException, stage: str) -> OperationIssueCode:
    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC:
            return OperationIssueCode.NO_SPACE_LEFT
        if exc.errno in (errno.EACCES, errno.EPERM):
            return OperationIssueCode.PERMISSION_DENIED
        if exc.errno == errno.ENOENT:
            if stage.startswith(("scanning", "copy.source", "copy.read", "verification")):
                return OperationIssueCode.SOURCE_NOT_FOUND
            return OperationIssueCode.DESTINATION_UNAVAILABLE
        if stage in ("copy.atomic_replace", "report.replace"):
            return OperationIssueCode.ATOMIC_REPLACE_FAILED
        if "fsync" in stage:
            return OperationIssueCode.FSYNC_FAILED
        if stage in ("copy.read_source", "verification", "verification.size"):
            return OperationIssueCode.READ_FAILED
        if stage.startswith("verification."):
            return OperationIssueCode.HASH_CALCULATION_FAILED
        if stage.startswith("copy.write") or stage.startswith("copy.create"):
            return OperationIssueCode.WRITE_FAILED
        if stage.startswith("report."):
            return OperationIssueCode.REPORT_WRITE_FAILED
        if stage == "scanning":
            return OperationIssueCode.SCAN_FAILED
        if exc.errno == errno.EIO:
            return OperationIssueCode.READ_FAILED
    return OperationIssueCode.UNKNOWN_ERROR


def create_operation_issue(
    exc: BaseException,
    *,
    stage: str,
    source_path: str | None = None,
    destination_path: str | None = None,
    file_name: str | None = None,
    fatal: bool = False,
    code: OperationIssueCode | str | None = None,
    message: str | None = None,
) -> OperationIssue:
    resolved_code = code or _default_code(exc, stage)
    if isinstance(resolved_code, OperationIssueCode):
        resolved_code = resolved_code.value
    return OperationIssue(
        stage=stage,
        code=resolved_code,
        message=message or _STAGE_MESSAGES.get(stage, "Произошла ошибка файловой операции"),
        source_path=str(source_path) if source_path is not None else None,
        destination_path=str(destination_path) if destination_path is not None else None,
        file_name=file_name,
        technical_message=str(exc) or type(exc).__name__,
        fatal=fatal,
    )


def create_message_issue(
    *,
    stage: str,
    code: OperationIssueCode | str,
    message: str,
    source_path: str | None = None,
    destination_path: str | None = None,
    file_name: str | None = None,
    technical_message: str | None = None,
    fatal: bool = False,
) -> OperationIssue:
    resolved_code = code.value if isinstance(code, OperationIssueCode) else code
    return OperationIssue(
        stage=stage,
        code=resolved_code,
        message=message,
        source_path=str(source_path) if source_path is not None else None,
        destination_path=str(destination_path) if destination_path is not None else None,
        file_name=file_name,
        technical_message=technical_message,
        fatal=fatal,
    )
