"""
Модуль с компонентами для процесса резервного копирования.
Каждый компонент отвечает за свою область ответственности.
"""

from .file_copier import FileCopier
from .file_verifier import FileVerifier
from .copy_verification_result import CopyVerificationResult
from .backup_logger import BackupLogger
from .backup_notifier import BackupNotifier
from .backup_orchestrator import BackupOrchestrator
from .hash_storage import HashStorage
from .operation_issue import (
    OperationIssue,
    OperationIssueCode,
    create_message_issue,
    create_operation_issue,
)
from .operation_results import CopyResult, VerificationResult

__all__ = [
    'FileCopier',
    'FileVerifier',
    'CopyVerificationResult',
    'BackupLogger',
    'BackupNotifier',
    'BackupOrchestrator',
    'HashStorage',
    'OperationIssue',
    'OperationIssueCode',
    'create_message_issue',
    'create_operation_issue',
    'CopyResult',
    'VerificationResult',
]
