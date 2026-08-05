"""
Модуль для стратегий этапов процесса резервного копирования.
Использует паттерн Strategy для разделения этапов процесса.
"""

from abc import ABC, abstractmethod
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backup_orchestrator import BackupOrchestrator


logger = logging.getLogger(__name__)


class BackupStage(ABC):
    """Базовый класс для этапа процесса резервного копирования"""
    
    @abstractmethod
    def execute(self, orchestrator: 'BackupOrchestrator') -> None:
        """
        Выполняет этап процесса
        
        :param orchestrator: Экземпляр BackupOrchestrator
        """
        pass


class InitializationStage(BackupStage):
    """Этап инициализации процесса резервного копирования"""
    
    def execute(self, orchestrator: 'BackupOrchestrator') -> None:
        """Выполняет инициализацию процесса"""
        logger.debug("InitializationStage.execute() entry")
        
        orchestrator._initialize_sleep_prevention()
        orchestrator._scan_total_size()
        orchestrator._initialize_destination()
        logger.debug("InitializationStage complete")


class CopyingStage(BackupStage):
    """Этап копирования файлов"""
    
    def execute(self, orchestrator: 'BackupOrchestrator') -> None:
        """Выполняет копирование файлов"""
        orchestrator._copy_all_files()


class VerificationStage(BackupStage):
    """Этап проверки целостности файлов"""
    
    def execute(self, orchestrator: 'BackupOrchestrator') -> None:
        """Выполняет проверку целостности файлов"""
        orchestrator._verify_all_files()


class FinalizationStage(BackupStage):
    """Этап завершения процесса"""
    
    def execute(self, orchestrator: 'BackupOrchestrator') -> None:
        """Выполняет завершение процесса"""
        logger.debug("FinalizationStage.execute() entry")
        orchestrator._finalize_process()
        logger.debug("FinalizationStage complete")
