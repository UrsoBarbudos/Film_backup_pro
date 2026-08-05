from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional
from engine_modules.category_definitions import CATEGORY_DEFINITIONS
from paths import get_fallback_reports_dir
from ..completion_status import (
    COMPLETION_MESSAGES,
    BackupCompletionStatus,
    determine_completion_status,
)

logger = logging.getLogger(__name__)

class CompletionService:
    def finalize_process(self, orchestrator) -> None:
        """Завершает процесс: прогресс, статистика, логи, уведомления, callback"""
        logger.debug("_finalize_process() entry")
        orchestrator.end_time = datetime.now()

        marker_warnings = self.write_source_markers_if_eligible(orchestrator)

        logger.debug("Before _update_final_progress()")
        orchestrator._update_final_progress()
        logger.debug("After _update_final_progress()")

        stats = self.prepare_completion_stats(orchestrator)
        if marker_warnings:
            stats["warnings"] = marker_warnings

        logger.debug("Before _print_completion_summary()")
        orchestrator._print_completion_summary()
        logger.debug("After _print_completion_summary()")
        logger.debug("Before _create_md_log_if_needed()")
        log_path_md = self.create_md_log_if_needed(orchestrator)
        logger.debug("After _create_md_log_if_needed()")

        report_issue = getattr(orchestrator.backup_logger, "last_issue", None)
        if report_issue is not None:
            orchestrator.record_issue(report_issue, count_failure=False)
            marker_warnings.append(report_issue.message)
        stats = self.prepare_completion_stats(orchestrator)
        if marker_warnings:
            stats["warnings"] = marker_warnings
        status = determine_completion_status(stats)
        orchestrator.log_callback(COMPLETION_MESSAGES[status])
        if orchestrator.signals:
            self.emit_completion_signal(orchestrator, stats)
            logger.debug("After _emit_completion_signal()")

        logger.debug("Before _send_completion_notifications()")
        self.send_completion_notifications(orchestrator, stats, log_path_md)
        logger.debug("After _send_completion_notifications()")

        logger.debug("Before _call_success_callback()")
        if status is BackupCompletionStatus.SUCCESS:
            self.call_success_callback(orchestrator)
        logger.debug("After _call_success_callback() - _finalize_process() complete")

    def write_source_markers_if_eligible(self, orchestrator) -> list[str]:
        """Записывает отметки только после полностью успешной проверки."""
        service = getattr(orchestrator, "source_backup_marker_service", None)
        config = getattr(orchestrator, "config", None)
        if service is None or config is None:
            return []
        if not config.get("mark_source_after_verified_backup", True):
            return []
        if orchestrator.cancel_token.is_cancelled():
            return []
        if getattr(orchestrator, "failed_files", 0) != 0:
            return []
        if getattr(orchestrator, "verification_failed_files", 0) != 0:
            return []
        expected = len(getattr(orchestrator, "files_to_verify", []) or [])
        if getattr(orchestrator, "verified_files_count", 0) != expected:
            return []

        verified_at = datetime.now().astimezone()
        metadata = {
            "app_version": config.get("app_version", None),
            "destination_path": getattr(orchestrator, "destination_root", None),
            "verification_mode": getattr(orchestrator, "verification_mode", None),
            "source_file_count": getattr(orchestrator, "total_files", None),
            "source_total_bytes": getattr(orchestrator, "total_bytes", None),
        }
        try:
            service.write_markers(
                orchestrator.source_drives,
                verified_at=verified_at,
                metadata=metadata,
            )
            return []
        except (OSError, ValueError) as exc:
            warning = f"Не удалось сохранить отметку на исходном носителе: {exc}"
            logger.warning("%s", warning)
            orchestrator.log_callback(f"⚠️  {warning}")
            return [warning]

    def prepare_completion_stats(self, orchestrator) -> Dict:
        """Подготавливает единую статистику для успеха, отмены и ошибки."""
        copied_files = getattr(orchestrator, "copied_files", {}) or {}
        category_stats = {}
        for category in (definition.key for definition in CATEGORY_DEFINITIONS):
            if category in copied_files:
                category_stats[category] = {
                    "count": len(copied_files[category]),
                    "total_size": sum(f.get("size", 0) for f in copied_files[category]),
                }
            else:
                category_stats[category] = {"count": 0, "total_size": 0}

        end_time = getattr(orchestrator, "end_time", None) or datetime.now()
        return {
            "total_files": getattr(orchestrator, "total_files", 0),
            "successful_files": getattr(orchestrator, "successful_files", 0),
            "failed_files": getattr(orchestrator, "failed_files", 0),
            "verification_failed_files": getattr(
                orchestrator, "verification_failed_files", 0
            ),
            "verified_files": getattr(orchestrator, "verified_files_count", 0),
            "unverified_files": max(
                0,
                len(getattr(orchestrator, "files_to_verify", []) or [])
                - getattr(orchestrator, "verified_files_count", 0),
            ),
            "start_time": self._format_datetime(getattr(orchestrator, "start_time", None)),
            "end_time": self._format_datetime(end_time),
            "total_bytes": getattr(orchestrator, "total_bytes", 0),
            "copied_bytes": getattr(orchestrator, "copied_bytes", 0),
            "verification_read_bytes": getattr(
                orchestrator, "verification_read_bytes", 0
            ),
            "destination_path": getattr(orchestrator, "destination_root", None) or "",
            "source_drives": list(getattr(orchestrator, "source_drives", []) or []),
            "category_stats": category_stats,
            "issues": [
                issue.to_dict()
                for issue in list(getattr(orchestrator, "operation_issues", []) or [])
            ],
        }

    @staticmethod
    def _format_datetime(value) -> Optional[str]:
        """Возвращает стабильное строковое представление времени."""
        if isinstance(value, datetime):
            return value.isoformat()
        if value is None:
            return None
        return str(value)

    def prepare_completion_stats_safely(self, orchestrator) -> Optional[Dict]:
        """Безопасный вариант для аварийного завершения и отмены."""
        try:
            return self.prepare_completion_stats(orchestrator)
        except Exception as exc:  # noqa: BLE001 - статистика не должна скрывать исходную ошибку
            logger.warning("Не удалось подготовить статистику завершения: %s", exc)
            return None

    def emit_completion_signal(self, orchestrator, stats: Dict) -> None:
        """Отправляет сигнал о завершении с статистикой"""
        if not orchestrator.signals:
            return

        try:
            status = determine_completion_status(stats)
            orchestrator.signals.finished.emit(
                status.value, COMPLETION_MESSAGES[status], stats
            )
        except Exception as exc:  # noqa: BLE001 - legacy behavior
            logger.warning("Ошибка при передаче статистики: %s", exc)
            self.emit_fallback_completion_signal(orchestrator)

    def emit_fallback_completion_signal(self, orchestrator) -> None:
        """Отправляет сигнал о завершении без статистики (fallback)"""
        if not orchestrator.signals:
            return
        try:
            orchestrator.signals.finished.emit(
                BackupCompletionStatus.FAILED.value,
                COMPLETION_MESSAGES[BackupCompletionStatus.FAILED],
                None,
            )
        except Exception:  # noqa: BLE001
            pass

    def create_md_log_if_needed(self, orchestrator) -> Optional[str]:
        """Создает MD лог-файл если необходимо"""
        has_reportable_state = (
            orchestrator.successful_files > 0
            or bool(getattr(orchestrator, "operation_issues", []))
            or orchestrator.cancel_token.is_cancelled()
        )
        if not (orchestrator.create_md_log and has_reportable_state):
            if hasattr(orchestrator.backup_logger, "last_issue"):
                orchestrator.backup_logger.last_issue = None
            return None

        try:
            log_path = orchestrator.backup_logger.create_md_log_file(
                destination_root=orchestrator.destination_root,
                source_drives=orchestrator.source_drives,
                start_time=orchestrator.start_time,
                end_time=orchestrator.end_time or datetime.now(),
                total_files=orchestrator.total_files,
                successful_files=orchestrator.successful_files,
                failed_files=orchestrator.failed_files,
                copied_files=orchestrator.copied_files,
                file_system=orchestrator.file_system,
                issues=[
                    issue.to_dict()
                    for issue in list(getattr(orchestrator, "operation_issues", []) or [])
                ],
            )
            if log_path:
                orchestrator.log_callback(
                    f"📄 MD лог-файл создан: {orchestrator.file_system.basename(log_path)}"
                )
                return log_path

            primary_issue = getattr(orchestrator.backup_logger, "last_issue", None)
            if primary_issue is None:
                return log_path

            orchestrator.record_issue(
                primary_issue,
                count_failure=False,
                emit_status=False,
            )
            orchestrator.log_callback(
                "⚠️  Не удалось сохранить MD-отчёт на диске назначения; "
                "создаётся локальная резервная копия"
            )

            fallback_directory = get_fallback_reports_dir()
            fallback_path = orchestrator.backup_logger.create_md_log_file(
                destination_root=orchestrator.destination_root,
                source_drives=orchestrator.source_drives,
                start_time=orchestrator.start_time,
                end_time=orchestrator.end_time or datetime.now(),
                total_files=orchestrator.total_files,
                successful_files=orchestrator.successful_files,
                failed_files=orchestrator.failed_files,
                copied_files=orchestrator.copied_files,
                file_system=orchestrator.file_system,
                issues=[
                    issue.to_dict()
                    for issue in list(
                        getattr(orchestrator, "operation_issues", []) or []
                    )
                ],
                report_directory=fallback_directory,
            )
            if fallback_path:
                # Финализация должна по-прежнему сообщить об отказе основного отчёта.
                orchestrator.backup_logger.last_issue = primary_issue
                orchestrator.log_callback(
                    f"📄 Резервный MD-отчёт создан: {fallback_path}"
                )
                return fallback_path

            return fallback_path
        except Exception as exc:  # noqa: BLE001 - legacy behavior
            logger.exception("Ошибка при создании MD лог-файла: %s", exc)
            return None

    def send_completion_notifications(self, orchestrator, stats: Dict, log_path: Optional[str]) -> None:
        """Отправляет уведомления о завершении копирования"""
        notification_stats = {
            "total_files": stats["total_files"],
            "successful_files": stats["successful_files"],
            "failed_files": stats["failed_files"],
            "completion_status": determine_completion_status(stats).value,
            "verification_failed_files": stats["verification_failed_files"],
            "unverified_files": stats["unverified_files"],
            "start_time": stats["start_time"],
            "end_time": stats["end_time"],
            "total_bytes": stats["total_bytes"],
            "copied_bytes": stats["copied_bytes"],
            "destination_path": stats["destination_path"],
            "source_drives": stats["source_drives"],
        }
        orchestrator.backup_notifier.send_notifications(notification_stats, log_path)

    def call_success_callback(self, orchestrator) -> None:
        """Вызывает callback после успешного завершения"""
        if orchestrator.success_callback and orchestrator.successful_files > 0:
            try:
                orchestrator.success_callback()
            except Exception as exc:  # noqa: BLE001 - legacy behavior
                logger.warning("Ошибка при вызове success_callback: %s", exc)
