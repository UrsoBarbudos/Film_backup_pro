from __future__ import annotations

import logging

from ..exceptions import BackupCancelledError
from ..operation_issue import OperationIssue

logger = logging.getLogger(__name__)

class VerificationService:
    def verify_all_files(self, orchestrator) -> None:
        """Проверяет целостность всех скопированных файлов"""
        orchestrator._check_cancellation()

        orchestrator.current_stage = "verifying"
        orchestrator.log_callback("––– Этап 2: Проверка целостности файлов –––")

        # Сохраняем текущие счётчики: они могут включать «пропуски как дубликаты» и др.
        base_successful_files = getattr(orchestrator, "successful_files", 0)
        base_failed_files = getattr(orchestrator, "failed_files", 0)

        verified_files = 0
        verification_failed_files = 0

        total_files_to_verify = len(orchestrator.files_to_verify)
        orchestrator.log_callback(f"Начинаю проверку {total_files_to_verify} файлов...")

        for verify_index, verification_item in enumerate(orchestrator.files_to_verify, 1):
            src_file, dst_file, filename, category, file_size = verification_item[:5]
            copy_verification_result = (
                verification_item[5] if len(verification_item) > 5 else None
            )
            if self.is_file_already_verified(orchestrator, src_file, filename):
                verified_files += 1
                continue

            orchestrator._check_cancellation()
            orchestrator._check_pause()

            orchestrator._update_verification_progress(verify_index, total_files_to_verify, filename)

            try:
                verification_result = orchestrator.file_verifier.verify_file(
                    src_file, dst_file, copy_verification_result
                )
            except BackupCancelledError:
                raise

            if verification_result.success:
                verified_files += 1
                orchestrator.verified_files_set.add(src_file)
            else:
                if self.handle_verification_failure(
                    orchestrator,
                    src_file,
                    dst_file,
                    filename,
                    verification_result.issue,
                ):
                    verified_files += 1
                else:
                    verification_failed_files += 1

        orchestrator.log_callback(
            f"✓ Проверка завершена. Проверено файлов: {verified_files}, ошибок: {verification_failed_files}"
        )

        # Не «перезатираем» successful_files: он считается на этапе копирования/дедупликации.
        # Добавляем только ошибки верификации к общему числу ошибок.
        orchestrator.verified_files_count = verified_files
        orchestrator.verification_failed_files = verification_failed_files
        orchestrator.successful_files = base_successful_files
        orchestrator.failed_files = base_failed_files + verification_failed_files

    def is_file_already_verified(self, orchestrator, src_file: str, filename: str) -> bool:
        """Проверяет, был ли файл уже проверен"""
        if src_file not in orchestrator.verified_files_set:
            return False

        if not orchestrator.file_system.exists(src_file):
            orchestrator.log_callback(f"⚠️  Файл {filename} был удален из источника, пропуск проверки")
            return True

        logger.debug("Файл уже проверен, пропускаю: %s", filename)
        orchestrator.log_callback(f"⏭️  Файл {filename} уже проверен, пропуск")
        return True

    def handle_verification_failure(
        self,
        orchestrator,
        src_file: str,
        dst_file: str,
        filename: str,
        issue: OperationIssue,
    ) -> bool:
        """
        Обрабатывает ошибку проверки файла.

        :return: True если нужно продолжить, False если отменено
        """
        while True:
            action = self.get_verification_action(orchestrator, src_file, dst_file, issue)

            if action == "recopy":
                retry_issue = self.retry_file_copy(
                    orchestrator, src_file, dst_file, filename
                )
                if retry_issue is None:
                    return True
                issue = retry_issue
                continue
            if action == "skip":
                # Сообщение уже выведено в лог callback'ом (backup_launcher).
                self.remove_invalid_copy(orchestrator, dst_file, filename)
                self._record_final_verification_issue(orchestrator, issue)
                return False

            # Неизвестное действие, закрытие диалога и явная отмена безопасно
            # трактуются одинаково: продолжать без решения нельзя.
            self.remove_invalid_copy(orchestrator, dst_file, filename)
            orchestrator.log_callback("❌ Проверка отменена пользователем")
            raise BackupCancelledError("Проверка отменена")

    @staticmethod
    def remove_invalid_copy(orchestrator, dst_file: str, filename: str) -> None:
        """Не оставляет неподтверждённый файл под именем готовой копии."""
        try:
            if orchestrator.file_system.exists(dst_file):
                orchestrator.file_system.remove(dst_file)
                orchestrator.log_callback(
                    f"Удалена копия, не прошедшая проверку: {filename}"
                )
        except OSError as exc:
            logger.error(
                "Не удалось удалить неподтверждённую копию %s: %s", dst_file, exc
            )
            orchestrator.log_callback(
                f"❌ Не удалось удалить неподтверждённую копию {filename}: {exc}"
            )

    def retry_file_copy(
        self, orchestrator, src_file: str, dst_file: str, filename: str
    ) -> OperationIssue | None:
        """Возвращает None при успехе или актуальную ошибку повторной попытки."""
        orchestrator.log_callback(f"🔄 Перекопирую файл: {filename}")

        recopy_result = orchestrator.file_copier.copy_file(
            src_file,
            dst_file,
            orchestrator.destination_root,
            progress_callback=None,
            base_copied_bytes=0,
            total_bytes=0,
        )

        if not recopy_result.success:
            orchestrator.log_callback(f"❌ Не удалось перекопировать файл: {filename}")
            return recopy_result.issue

        verify_retry_result = orchestrator.file_verifier.verify_file(
            src_file, dst_file, recopy_result.verification
        )

        if verify_retry_result.success:
            orchestrator.verified_files_set.add(src_file)
            orchestrator.log_callback(f"✅ Файл {filename} успешно перекопирован и проверен")
            return None

        orchestrator.log_callback(
            f"❌ Файл {filename} все еще не прошел проверку после перекопирования"
        )
        return verify_retry_result.issue

    def get_verification_action(
        self,
        orchestrator,
        source_path: str,
        destination_path: str,
        issue: OperationIssue,
    ) -> str:
        """Запрашивает действие пользователя при ошибке проверки через UI"""
        if orchestrator.verification_action_callback:
            try:
                details = issue.message
                if issue.technical_message:
                    details += f"\n\nТехническая информация: {issue.technical_message}"
                return orchestrator.verification_action_callback(
                    source_path, destination_path, details
                )
            except Exception as exc:  # noqa: BLE001 - legacy behavior
                logger.warning("Ошибка при запросе действия пользователя: %s", exc)
                return "cancel"
        return "cancel"

    @staticmethod
    def _record_final_verification_issue(orchestrator, issue: OperationIssue) -> None:
        if hasattr(orchestrator, "record_issue"):
            orchestrator.record_issue(issue, count_failure=False)
        else:
            orchestrator.operation_issues = getattr(orchestrator, "operation_issues", [])
            orchestrator.operation_issues.append(issue)
