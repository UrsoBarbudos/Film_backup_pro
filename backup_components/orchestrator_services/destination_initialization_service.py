from __future__ import annotations

import logging

from utils import format_size
from engine_modules.scanning import scan_sources_unified
from ..operation_issue import OperationIssueCode, create_operation_issue

logger = logging.getLogger(__name__)


class DestinationInitializationService:
    def initialize_sleep_prevention(self, orchestrator) -> None:
        """Инициализирует предотвращение спящего режима"""
        if orchestrator.prevent_sleep:
            orchestrator.sleep_manager = orchestrator._sleep_prevention_factory()
            orchestrator.sleep_manager.__enter__()
            orchestrator.log_callback("Предотвращение спящего режима включено")

    def scan_total_size(self, orchestrator) -> None:
        """Выполняет предварительное сканирование для подсчета общего объема"""
        orchestrator._check_cancellation()

        if orchestrator.progress_batcher or orchestrator.progress_callback:
            orchestrator.log_callback("Начинаю предварительное сканирование для подсчёта объёма...")
            try:
                def should_cancel() -> bool:
                    return orchestrator.cancel_token.is_cancelled() if orchestrator.cancel_token else False
                
                scan_result = orchestrator.retry_handler.retry_on_temporary_error(
                    scan_sources_unified,
                    orchestrator.source_drives,
                    orchestrator.destination_root,
                    orchestrator.log_callback,
                    orchestrator.file_system,
                    should_cancel=should_cancel,
                )
                
                # Сохраняем результат сканирования
                orchestrator.scan_result = scan_result
                orchestrator.total_bytes = scan_result.total_size
                orchestrator.total_files = scan_result.total_files
                orchestrator.all_files_to_copy = scan_result.files_list
                for issue in scan_result.issues:
                    orchestrator.record_issue(issue)
                
                if orchestrator.total_bytes > 0:
                    orchestrator.log_callback(
                        f"✓ Общий объём для копирования: {format_size(orchestrator.total_bytes)}"
                    )
                else:
                    orchestrator.log_callback(
                        "⚠️  Не удалось определить общий объём, прогресс будет отображаться только по скопированному объёму"
                    )
            except Exception as exc:  # noqa: BLE001 - поведение legacy
                logger.warning("Ошибка при предварительном сканировании: %s", exc)
                orchestrator.log_callback(
                    f"⚠️  Ошибка при сканировании: {exc}. Продолжаю без предварительного сканирования."
                )
                orchestrator.record_issue(
                    create_operation_issue(
                        exc,
                        stage="scanning",
                        destination_path=orchestrator.destination_root,
                        code=OperationIssueCode.SCAN_FAILED,
                        message="Не удалось выполнить предварительное сканирование",
                    )
                )
                orchestrator.total_bytes = 0
                orchestrator.scan_result = None
                orchestrator.all_files_to_copy = []

    def initialize_destination(self, orchestrator) -> None:
        """Проверяет, что выбранное назначение доступно, не меняя его семантику."""
        orchestrator._check_cancellation()
        destination = orchestrator.destination_root
        exists = orchestrator.retry_handler.retry_on_temporary_error(
            orchestrator.file_system.exists, destination
        )
        is_directory = exists and orchestrator.retry_handler.retry_on_temporary_error(
            orchestrator.file_system.isdir, destination
        )
        if not is_directory:
            raise ValueError(f"Папка назначения недоступна: {destination}")
        orchestrator.log_callback(f"Назначение: {destination}")
