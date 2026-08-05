from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .copy_verification_result import CopyVerificationResult
from .operation_issue import OperationIssue


@dataclass(frozen=True, slots=True)
class CopyResult:
    success: bool
    copied_size: int
    verification: Optional[CopyVerificationResult] = None
    issue: Optional[OperationIssue] = None

    def __post_init__(self) -> None:
        if self.success and self.issue is not None:
            raise ValueError("Успешный результат копирования не может содержать ошибку")
        if not self.success and self.issue is None:
            raise ValueError("Неуспешный результат копирования должен содержать ошибку")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    success: bool
    issue: Optional[OperationIssue] = None

    def __post_init__(self) -> None:
        if self.success and self.issue is not None:
            raise ValueError("Успешный результат проверки не может содержать ошибку")
        if not self.success and self.issue is None:
            raise ValueError("Неуспешный результат проверки должен содержать ошибку")
