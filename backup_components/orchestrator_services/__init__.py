"""
Сервисы, содержащие логику этапов бэкапа.

Цель: разгрузить BackupOrchestrator и улучшить SRP/KISS,
оставив оркестратор координатором процесса.
"""

from .destination_initialization_service import DestinationInitializationService
from .copy_plan_and_execute_service import CopyPlanAndExecuteService
from .verification_service import VerificationService
from .progress_reporting_service import ProgressReportingService
from .completion_service import CompletionService

__all__ = [
    "DestinationInitializationService",
    "CopyPlanAndExecuteService",
    "VerificationService",
    "ProgressReportingService",
    "CompletionService",
]
