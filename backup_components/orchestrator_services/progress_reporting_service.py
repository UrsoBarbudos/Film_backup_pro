from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ProgressReportingService:
    def update_progress(self, orchestrator) -> None:
        """Обновляет прогресс копирования"""
        if not orchestrator.progress_callback and not orchestrator.progress_batcher:
            return

        completed_without_errors = (
            getattr(orchestrator, "copy_plan_completed", False)
            and getattr(orchestrator, "failed_files", 0) == 0
        )
        percent = (
            100
            if completed_without_errors
            else int((orchestrator.copied_bytes / orchestrator.total_bytes * 100))
            if orchestrator.total_bytes > 0
            else 0
        )
        current_time = datetime.now()
        time_delta = (current_time - orchestrator.last_update_time).total_seconds()

        if time_delta > 0:
            if orchestrator.copied_bytes >= orchestrator.last_copied_bytes:
                bytes_delta = orchestrator.copied_bytes - orchestrator.last_copied_bytes
            else:
                bytes_delta = 0
            speed_mbps = (bytes_delta / (1024 * 1024)) / time_delta
        else:
            speed_mbps = 0.0

        if orchestrator.progress_batcher:
            orchestrator.progress_batcher.update_progress(
                percent,
                orchestrator.copied_bytes,
                orchestrator.total_bytes,
                speed_mbps,
                orchestrator.current_file,
            )
        elif orchestrator.progress_callback:
            orchestrator.progress_callback(
                percent,
                orchestrator.copied_bytes,
                orchestrator.total_bytes,
                speed_mbps,
                orchestrator.current_file,
            )

        orchestrator.last_update_time = current_time
        orchestrator.last_copied_bytes = orchestrator.copied_bytes

    def update_verification_progress(
        self, orchestrator, verify_index: int, total_files: int, filename: str
    ) -> None:
        """Обновляет прогресс проверки"""
        orchestrator.current_file = f"Проверка: {filename}"

        if orchestrator.progress_callback or orchestrator.progress_batcher:
            copy_percent = 50
            verify_percent = int((verify_index / total_files * 50)) if total_files > 0 else 0
            total_percent = copy_percent + verify_percent

            if orchestrator.progress_batcher:
                orchestrator.progress_batcher.update_progress(
                    total_percent,
                    orchestrator.copied_bytes,
                    orchestrator.total_bytes,
                    0.0,
                    orchestrator.current_file,
                )
            elif orchestrator.progress_callback:
                orchestrator.progress_callback(
                    total_percent,
                    orchestrator.copied_bytes,
                    orchestrator.total_bytes,
                    0.0,
                    orchestrator.current_file,
                )

        if orchestrator.signals:
            try:
                orchestrator.signals.status_updated.emit(
                    f"Проверка файла {verify_index} из {total_files}: {filename}"
                )
            except Exception:  # noqa: BLE001
                pass

    def update_final_progress(self, orchestrator) -> None:
        """Обновляет финальный прогресс"""
        logger.debug(
            "_update_final_progress() entry (has_progress_callback=%s, has_progress_batcher=%s)",
            orchestrator.progress_callback is not None,
            orchestrator.progress_batcher is not None,
        )
        if not orchestrator.progress_callback and not orchestrator.progress_batcher:
            logger.debug("_update_final_progress(): early return (no callbacks)")
            return

        completed_without_errors = (
            getattr(orchestrator, "copy_plan_completed", False)
            and getattr(orchestrator, "failed_files", 0) == 0
        )
        percent = 100 if completed_without_errors or (
            orchestrator.total_bytes > 0 and orchestrator.copied_bytes >= orchestrator.total_bytes
        ) else (
            int((orchestrator.copied_bytes / orchestrator.total_bytes * 100)) if orchestrator.total_bytes > 0 else 0
        )
        current_time = datetime.now()
        time_delta = (current_time - orchestrator.last_update_time).total_seconds()

        if time_delta > 0:
            if orchestrator.copied_bytes >= orchestrator.last_copied_bytes:
                bytes_delta = orchestrator.copied_bytes - orchestrator.last_copied_bytes
            else:
                bytes_delta = 0
            speed_mbps = (bytes_delta / (1024 * 1024)) / time_delta
        else:
            speed_mbps = 0.0

        logger.debug(
            "Final progress update (percent=%d, has_progress_batcher=%s, has_progress_callback=%s)",
            percent,
            orchestrator.progress_batcher is not None,
            orchestrator.progress_callback is not None,
        )
        if orchestrator.progress_batcher:
            orchestrator.progress_batcher.update_progress(
                percent, orchestrator.copied_bytes, orchestrator.total_bytes, speed_mbps, ""
            )
            orchestrator.progress_batcher.force_update()
        elif orchestrator.progress_callback:
            orchestrator.progress_callback(
                percent, orchestrator.copied_bytes, orchestrator.total_bytes, speed_mbps, ""
            )
        logger.debug("_update_final_progress() exit")
