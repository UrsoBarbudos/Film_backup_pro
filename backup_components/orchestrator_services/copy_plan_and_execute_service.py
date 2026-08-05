from __future__ import annotations

import logging
import os
from pathlib import Path, PurePath
from typing import Optional

from engine_modules.categories import (
    get_file_category,
    is_system_file,
)
from engine_modules.scanning import PlannedCopy
from ..operation_issue import OperationIssue, OperationIssueCode, create_message_issue
from utils import safe_add_bytes, validate_file_size

logger = logging.getLogger(__name__)


class CopyPlanAndExecuteService:
    def _resolve_destination_conflict(
        self,
        orchestrator,
        *,
        src_file: str,
        dst_file: str,
        filename: str,
    ) -> Optional[str]:
        """
        Если файл назначения не существует — возвращает dst_file.
        Если существует — запрашивает действие (политика или callback): skip -> None, replace -> dst_file, keep_both -> новый путь.
        """
        if not orchestrator.file_system.exists(dst_file):
            return dst_file

        callback = getattr(orchestrator, "copy_conflict_action_callback", None)
        policy = getattr(orchestrator, "copy_conflict_policy", None)

        if policy is not None:
            action = policy
        elif callback:
            action, apply_to_all = callback(src_file, dst_file, filename)
            orchestrator._check_cancellation()
            if apply_to_all:
                orchestrator.copy_conflict_policy = action
        else:
            # Нет callback — по умолчанию оставляем оба (уникальное имя)
            action = "keep_both"

        if action == "skip":
            orchestrator.log_callback(f"⏭️ Пропуск (файл уже существует): {filename}")
            return None
        if action == "replace":
            orchestrator.log_callback(f"🔄 Замена существующего файла: {filename}")
            return dst_file
        # keep_both
        dest_dir = orchestrator.file_system.dirname(dst_file)
        unique_path = self._generate_unique_path_in_dir(orchestrator, dest_dir, filename)
        orchestrator.log_callback(f"📄 Оставить оба, копирую как: {orchestrator.file_system.basename(unique_path)}")
        return unique_path

    def _generate_unique_path_in_dir(
        self, orchestrator, dest_dir: str, filename: str
    ) -> str:
        """Генерирует уникальный путь в папке (имя_1.ext, имя_2.ext, ...)."""
        p = PurePath(filename)
        base_name, ext = p.stem, p.suffix
        counter = 1
        candidate = f"{base_name}_{counter}{ext}" if base_name else f"file_{counter}{ext}"
        full_path = orchestrator.file_system.join(dest_dir, candidate)
        while orchestrator.file_system.exists(full_path):
            counter += 1
            candidate = f"{base_name}_{counter}{ext}" if base_name else f"file_{counter}{ext}"
            full_path = orchestrator.file_system.join(dest_dir, candidate)
        return full_path

    def copy_all_files(self, orchestrator) -> None:
        """Копирует все файлы из источников"""
        orchestrator.copy_conflict_policy = None
        orchestrator.log_callback("––– Этап 1: Копирование файлов –––")

        # Используем результат единого сканирования, если он доступен
        if not orchestrator.all_files_to_copy:
            if orchestrator.scan_result:
                # Используем список файлов из результата сканирования
                orchestrator.all_files_to_copy = orchestrator.scan_result.files_list
                orchestrator.log_callback(f"✓ Использован список из предварительного сканирования: {len(orchestrator.all_files_to_copy)} файлов")
            else:
                # Fallback для legacy пути (если сканирование не было выполнено)
                orchestrator.log_callback("📋 Построение полного списка файлов для копирования...")
                from engine_modules.scanning import scan_sources_unified
                
                def should_cancel() -> bool:
                    return orchestrator.cancel_token.is_cancelled() if orchestrator.cancel_token else False
                
                scan_result = scan_sources_unified(
                    orchestrator.source_drives,
                    orchestrator.destination_root,
                    orchestrator.log_callback,
                    orchestrator.file_system,
                    should_cancel=should_cancel,
                )
                orchestrator.scan_result = scan_result
                orchestrator.all_files_to_copy = scan_result.files_list
                for issue in scan_result.issues:
                    if hasattr(orchestrator, "record_issue"):
                        orchestrator.record_issue(issue)
                orchestrator.log_callback(f"✓ Найдено {len(orchestrator.all_files_to_copy)} файлов для копирования")

        plan = list(orchestrator.all_files_to_copy)
        orchestrator.total_files = len(plan)
        orchestrator.total_bytes = sum(item.size for item in plan)
        orchestrator.planned_category_stats = self._calculate_category_stats(plan)

        logger.debug("Starting copy plan iteration (files_count=%d)", len(plan))
        for item in plan:
            orchestrator._check_cancellation()
            orchestrator._check_pause()
            self._execute_planned_copy(orchestrator, item)

        orchestrator.copy_plan_completed = True
        if orchestrator.progress_batcher or orchestrator.progress_callback:
            orchestrator._update_progress()
        orchestrator.log_callback(f"✓ Копирование завершено. Скопировано файлов: {orchestrator.successful_files}")

    @staticmethod
    def _calculate_category_stats(plan: list[PlannedCopy]) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for item in plan:
            category = item.category or "Other"
            category_stats = stats.setdefault(category, {"count": 0, "total_size": 0})
            category_stats["count"] += 1
            category_stats["total_size"] += item.size
        return stats

    def _execute_planned_copy(self, orchestrator, item: PlannedCopy) -> None:
        src_file = str(item.source_path)
        filename = item.source_path.name
        dst_file = orchestrator.file_system.join(
            orchestrator.destination_root, *item.relative_path.parts
        )

        issue = self._validate_planned_copy(orchestrator, item, dst_file)
        if issue:
            self._record_planned_copy_error(orchestrator, issue)
            return

        dst_file = self._resolve_destination_conflict(
            orchestrator,
            src_file=src_file,
            dst_file=dst_file,
            filename=filename,
        )
        if dst_file is None:
            orchestrator.skipped_files = getattr(orchestrator, "skipped_files", 0) + 1
            orchestrator.skipped_bytes = safe_add_bytes(
                getattr(orchestrator, "skipped_bytes", 0), item.size
            )
            orchestrator.total_bytes = max(0, orchestrator.total_bytes - item.size)
            if orchestrator.progress_batcher or orchestrator.progress_callback:
                orchestrator._update_progress()
            return

        self.copy_file_from_directory(
            orchestrator,
            src_file,
            dst_file,
            filename,
            item.category or get_file_category(filename),
        )

    def _validate_planned_copy(
        self, orchestrator, item: PlannedCopy, dst_file: str
    ) -> Optional[OperationIssue]:
        """Минимально перепроверяет элемент, не перестраивая план."""
        fs = orchestrator.file_system
        src_file = str(item.source_path)

        if not fs.exists(src_file):
            return create_message_issue(
                stage="planning",
                code=OperationIssueCode.SOURCE_NOT_FOUND,
                message="Исходный файл удалён после сканирования",
                source_path=src_file,
                destination_path=dst_file,
                file_name=item.source_path.name,
            )
        if not fs.isfile(src_file):
            return create_message_issue(
                stage="planning",
                code=OperationIssueCode.VALIDATION_FAILED,
                message="Источник больше не является поддерживаемым файлом",
                source_path=src_file,
                destination_path=dst_file,
                file_name=item.source_path.name,
            )
        if not self._is_destination_inside_root(orchestrator.destination_root, dst_file):
            return create_message_issue(
                stage="planning",
                code=OperationIssueCode.VALIDATION_FAILED,
                message="Путь назначения выходит за пределы выбранного корня",
                source_path=src_file,
                destination_path=dst_file,
                file_name=item.source_path.name,
            )

        try:
            current_size = fs.getsize(src_file)
            current_modified_ns = self._get_modified_ns(fs, src_file)
        except (OSError, FileNotFoundError, PermissionError) as exc:
            return create_message_issue(
                stage="planning",
                code=OperationIssueCode.SOURCE_UNREADABLE,
                message="Исходный файл недоступен для чтения",
                source_path=src_file,
                destination_path=dst_file,
                file_name=item.source_path.name,
                technical_message=str(exc),
            )

        if current_size != item.size:
            technical_message = f"размер: {item.size} → {current_size}"
            return create_message_issue(
                stage="planning",
                code=OperationIssueCode.SOURCE_CHANGED,
                message="Исходный файл изменён после сканирования",
                source_path=src_file,
                destination_path=dst_file,
                file_name=item.source_path.name,
                technical_message=technical_message,
            )
        if item.modified_ns is not None and current_modified_ns != item.modified_ns:
            return create_message_issue(
                stage="planning",
                code=OperationIssueCode.SOURCE_CHANGED,
                message="Исходный файл изменён после сканирования",
                source_path=src_file,
                destination_path=dst_file,
                file_name=item.source_path.name,
                technical_message="mtime_ns не совпадает",
            )
        return None

    @staticmethod
    def _get_modified_ns(file_system, path: str) -> int | None:
        try:
            getmtime_ns = getattr(file_system, "getmtime_ns", None)
            if getmtime_ns is not None:
                return int(getmtime_ns(path))
            return int(file_system.getmtime(path) * 1_000_000_000)
        except (OSError, FileNotFoundError, PermissionError):
            return None

    @staticmethod
    def _is_destination_inside_root(destination_root: str, destination_path: str) -> bool:
        try:
            root = os.path.realpath(destination_root)
            destination = os.path.realpath(destination_path)
            return os.path.commonpath((root, destination)) == root
        except ValueError:
            return False

    @staticmethod
    def _record_planned_copy_error(orchestrator, issue: OperationIssue) -> None:
        if hasattr(orchestrator, "record_issue"):
            orchestrator.record_issue(issue)
        else:
            orchestrator.operation_issues = getattr(orchestrator, "operation_issues", [])
            orchestrator.operation_issues.append(issue)
            orchestrator.failed_files += 1
        error_msg = f"❌ Файл {issue.file_name or issue.source_path} не скопирован: {issue.message}"
        if issue.technical_message:
            error_msg += f" ({issue.technical_message})"
        logger.error("%s", error_msg)
        orchestrator.log_callback(error_msg)
        if orchestrator.signals and not hasattr(orchestrator, "record_issue"):
            try:
                orchestrator.signals.status_updated.emit(error_msg)
            except Exception:  # noqa: BLE001 - ошибка UI-сигнала не скрывает исходную
                logger.debug("Не удалось отправить статус ошибки в UI", exc_info=True)

    def process_single_file(self, orchestrator, source_path: str) -> None:
        """Обрабатывает отдельный файл"""
        orchestrator._check_cancellation()

        filename = orchestrator.file_system.basename(source_path)
        if is_system_file(filename):
            logger.debug("Пропущен системный файл: %s", filename)
            return

        category = get_file_category(filename)
        dst_file = self.prepare_file_destination(orchestrator, source_path, filename, category)
        if not dst_file:
            return

        dst_file = self._resolve_destination_conflict(
            orchestrator, src_file=source_path, dst_file=dst_file, filename=filename
        )
        if dst_file is None:
            return

        self.handle_single_file_copy(orchestrator, source_path, dst_file, filename, category)

    def prepare_file_destination(
        self, orchestrator, source_path: str, filename: str, category: str
    ) -> Optional[str]:
        """Подготавливает путь назначения для файла"""
        dst_file = orchestrator.file_system.join(orchestrator.destination_root, filename)

        logger.debug("Копирование файла: %s -> категория: %s", filename, category)
        logger.debug("Путь назначения: %s", dst_file)
        return dst_file

    def generate_unique_filename(
        self, orchestrator, dest_dir: str, filename: str, file_number: int
    ) -> Optional[str]:
        """Генерирует уникальное имя файла если файл с таким именем уже существует"""
        p = PurePath(filename)
        base_name, ext = p.stem, p.suffix
        counter = 1
        numbered_filename = f"[{file_number}] {base_name}_{counter}{ext}"
        dst_file = orchestrator.file_system.join(dest_dir, numbered_filename)

        while orchestrator.file_system.exists(dst_file):
            counter += 1
            numbered_filename = f"[{file_number}] {base_name}_{counter}{ext}"
            dst_file = orchestrator.file_system.join(dest_dir, numbered_filename)

        if counter > 1:
            orchestrator.log_callback(
                f"⚠️  Файл с таким именем уже существует, переименован в: {numbered_filename}"
            )

        return numbered_filename

    def handle_single_file_copy(
        self,
        orchestrator,
        source_path: str,
        dst_file: str,
        filename: str,
        category: str,
    ) -> None:
        """Выполняет копирование одного файла"""
        progress_cb = (
            orchestrator.progress_batcher.update_progress
            if orchestrator.progress_batcher
            else orchestrator.progress_callback
        )
        result = orchestrator.file_copier.copy_file(
            source_path,
            dst_file,
            orchestrator.destination_root,
            progress_cb,
            orchestrator.last_copied_bytes,
            orchestrator.total_bytes,
        )

        if result.success:
            file_size = result.copied_size
            orchestrator.last_copied_bytes = safe_add_bytes(orchestrator.last_copied_bytes, file_size)
            orchestrator.copied_bytes = safe_add_bytes(orchestrator.copied_bytes, file_size)
            self.validate_single_file_copy(
                orchestrator,
                source_path,
                dst_file,
                filename,
                category,
                result.verification,
            )
        else:
            self._record_copy_issue(orchestrator, result.issue, filename)

    def validate_copied_file(
        self,
        orchestrator,
        *,
        src_file: str,
        dst_file: str,
        filename: str,
        category: Optional[str] = None,
        update_copied_bytes: bool = False,
        log_success: bool = False,
        verification_result=None,
    ) -> bool:
        """Валидирует скопированный файл (проверяет размер)"""
        is_valid, error_message = validate_file_size(src_file, dst_file, orchestrator.file_system)

        if is_valid:
            source_size = orchestrator.file_system.getsize(src_file)
            orchestrator.successful_files += 1

            if category is None:
                category = get_file_category(filename)

            if update_copied_bytes:
                orchestrator.copied_bytes = safe_add_bytes(orchestrator.copied_bytes, source_size)

            orchestrator.files_to_verify.append(
                (src_file, dst_file, filename, category, source_size, verification_result)
            )

            if log_success:
                orchestrator.log_callback(f"✓ Файл {filename} скопирован в категорию {category}")

            return True

        error_msg = f"⚠️ Файл {filename} скопирован не полностью. {error_message}. Пропуск проверки."
        orchestrator.log_callback(error_msg)
        issue = create_message_issue(
            stage="copy.final_size_validation",
            code=OperationIssueCode.FILE_SIZE_MISMATCH,
            message="Размер скопированного файла не совпадает с исходным файлом",
            source_path=src_file,
            destination_path=dst_file,
            file_name=filename,
            technical_message=error_message,
        )
        if hasattr(orchestrator, "record_issue"):
            orchestrator.record_issue(issue)
        else:
            orchestrator.operation_issues = getattr(orchestrator, "operation_issues", [])
            orchestrator.operation_issues.append(issue)
            orchestrator.failed_files += 1
        return False

    def validate_single_file_copy(
        self, orchestrator, source_path: str, dst_file: str, filename: str, category: str,
        verification_result=None,
    ) -> None:
        """Валидирует скопированный файл (проверяет размер)"""
        self.validate_copied_file(
            orchestrator,
            src_file=source_path,
            dst_file=dst_file,
            filename=filename,
            category=category,
            update_copied_bytes=False,
            log_success=True,
            verification_result=verification_result,
        )

    def process_directory(self, orchestrator, source_path: str) -> None:
        """Исполняет часть готового плана, относящуюся к директории."""
        source_root = Path(source_path)
        matching_items = [
            item
            for item in orchestrator.all_files_to_copy
            if item.source_root == source_root and not item.is_single_file
        ]
        for item in matching_items:
            orchestrator._check_cancellation()
            orchestrator._check_pause()
            self._execute_planned_copy(orchestrator, item)
        logger.info("Обработано элементов плана с источника %s: %d", source_path, len(matching_items))

    def copy_file_from_directory(
        self, orchestrator, src_file: str, dst_file: str, filename: str, category: str
    ) -> None:
        """Копирует один файл из директории"""
        orchestrator.current_file = src_file
        if orchestrator.progress_batcher or orchestrator.progress_callback:
            orchestrator._update_progress()

        progress_cb = (
            orchestrator.progress_batcher.update_progress
            if orchestrator.progress_batcher
            else orchestrator.progress_callback
        )
        result = orchestrator.file_copier.copy_file(
            src_file,
            dst_file,
            orchestrator.destination_root,
            progress_cb,
            base_copied_bytes=orchestrator.copied_bytes,
            total_bytes=orchestrator.total_bytes,
        )

        self.handle_file_copy_result(
            orchestrator, src_file, dst_file, filename, category, result.success,
            result.copied_size, result.verification, result.issue
        )

    def handle_file_copy_result(
        self,
        orchestrator,
        src_file: str,
        dst_file: str,
        filename: str,
        category: str,
        success: bool,
        file_size: int,
        verification_result=None,
        issue: Optional[OperationIssue] = None,
    ) -> None:
        """Обрабатывает результат копирования файла"""
        if not success:
            self._record_copy_issue(orchestrator, issue, filename)
            return

        file_size_valid = self.validate_file_copy(
            orchestrator, src_file, dst_file, filename, verification_result
        )

        if file_size_valid:
            if orchestrator.create_md_log:
                self.save_file_info_for_log(orchestrator, dst_file, category, file_size)

            if orchestrator.progress_batcher or orchestrator.progress_callback:
                orchestrator._update_progress()

    def validate_file_copy(
        self, orchestrator, src_file: str, dst_file: str, filename: str,
        verification_result=None,
    ) -> bool:
        """Валидирует скопированный файл (проверяет размер)"""
        return self.validate_copied_file(
            orchestrator,
            src_file=src_file,
            dst_file=dst_file,
            filename=filename,
            category=None,
            update_copied_bytes=True,
            log_success=False,
            verification_result=verification_result,
        )

    def save_file_info_for_log(self, orchestrator, dst_file: str, category: str, file_size: int) -> None:
        """Сохраняет информацию о файле для MD лог-файла"""
        try:
            if not file_size:
                file_size = orchestrator.file_system.getsize(dst_file)
            orchestrator.copied_files[category].append({"path": dst_file, "size": file_size})
        except Exception as exc:  # noqa: BLE001 - legacy behavior
            logger.warning("Не удалось получить размер файла %s: %s", dst_file, exc)

    @staticmethod
    def _record_copy_issue(
        orchestrator, issue: Optional[OperationIssue], filename: str
    ) -> None:
        if issue is None:
            issue = create_message_issue(
                stage="copying",
                code=OperationIssueCode.UNKNOWN_ERROR,
                message="Файл не был успешно скопирован",
                file_name=filename,
            )
        if hasattr(orchestrator, "record_issue"):
            orchestrator.record_issue(issue)
        else:
            orchestrator.operation_issues = getattr(orchestrator, "operation_issues", [])
            orchestrator.operation_issues.append(issue)
            orchestrator.failed_files += 1
        error_msg = f"❌ {issue.message}: {filename}"
        if issue.technical_message:
            error_msg += f" ({issue.technical_message})"
        orchestrator.log_callback(error_msg)
