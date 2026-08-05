"""Совместимый импорт модели ошибки из нейтрального архитектурного модуля."""

from operation_issue import (  # noqa: F401
    OperationIssue,
    OperationIssueCode,
    create_message_issue,
    create_operation_issue,
)

__all__ = [
    "OperationIssue",
    "OperationIssueCode",
    "create_message_issue",
    "create_operation_issue",
]
