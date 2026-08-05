from __future__ import annotations

import errno
import os
from datetime import datetime
from pathlib import Path

import pytest

from backup_components.backup_logger import BackupLogger
from backup_components.backup_orchestrator import BackupOrchestrator
from backup_components.backup_run_context import (
    BackupCallbacks,
    BackupDeps,
    BackupRunConfig,
    BackupTokens,
)
from backup_components.completion_status import BackupCompletionStatus, determine_completion_status
from backup_components.file_copier import FileCopier
from backup_components.file_verifier import FileVerifier
from backup_components.operation_issue import (
    OperationIssueCode,
    create_message_issue,
)
from backup_components.orchestrator_services.completion_service import CompletionService
from engine_modules.scanning import scan_sources_unified
from repositories.file_system_repository import FileSystemRepository


@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_code"),
    [
        ("makedirs", "copy.create_directory", "PERMISSION_DENIED"),
        ("temp", "copy.create_temporary_file", "NO_SPACE_LEFT"),
        ("read", "copy.read_source", "READ_FAILED"),
        ("write", "copy.write_temporary_file", "WRITE_FAILED"),
        ("fsync", "copy.fsync_temporary_file", "FSYNC_FAILED"),
        ("replace", "copy.atomic_replace", "ATOMIC_REPLACE_FAILED"),
        ("directory_fsync", "copy.fsync_destination_directory", "FSYNC_FAILED"),
    ],
)
def test_file_copier_returns_precise_structured_issue(
    tmp_path: Path, failure: str, expected_stage: str, expected_code: str
):
    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"footage")

    class FailingFileSystem(FileSystemRepository):
        def makedirs(self, path: str, exist_ok: bool = False) -> None:
            if failure == "makedirs":
                raise OSError(errno.EACCES, "directory denied")
            super().makedirs(path, exist_ok)

        def create_temp_file(self, directory: str, prefix: str, suffix: str) -> str:
            if failure == "temp":
                raise OSError(errno.ENOSPC, "disk full")
            return super().create_temp_file(directory, prefix, suffix)

        def open(self, path: str, mode: str, *args, **kwargs):
            if failure == "read" and path == str(source) and mode == "rb":
                raise OSError(errno.EIO, "source read failed")
            if failure == "write" and mode == "wb" and path.endswith(".partial"):
                raise OSError(errno.EIO, "temporary write failed")
            return super().open(path, mode, *args, **kwargs)

        def fsync_file(self, file_object) -> None:
            if failure == "fsync":
                raise OSError(errno.EIO, "file fsync failed")
            super().fsync_file(file_object)

        def replace(self, source_path: str, destination_path: str) -> None:
            if failure == "replace":
                raise OSError(errno.EIO, "replace failed")
            super().replace(source_path, destination_path)

        def fsync_directory(self, path: str) -> None:
            if failure == "directory_fsync":
                raise OSError(errno.EIO, "directory fsync failed")
            super().fsync_directory(path)

    result = FileCopier(
        file_system=FailingFileSystem(), verification_mode="full"
    ).copy_file(str(source), str(destination))

    assert result.success is False
    assert result.issue is not None
    assert result.issue.stage == expected_stage
    assert result.issue.code == expected_code
    assert result.issue.source_path == str(source)
    assert result.issue.destination_path == str(destination)
    assert result.issue.technical_message
    if failure == "directory_fsync":
        assert destination.exists()
        assert "опубликован" in result.issue.message.lower()
    else:
        assert list(tmp_path.glob(".*.partial")) == []


def test_verification_result_preserves_both_paths(tmp_path: Path):
    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"source")
    destination.write_bytes(b"different-size")

    result = FileVerifier(
        file_system=FileSystemRepository(), verification_mode="fast"
    ).verify_file(str(source), str(destination))

    assert result.success is False
    assert result.issue.code == "FILE_SIZE_MISMATCH"
    assert result.issue.source_path == str(source)
    assert result.issue.destination_path == str(destination)


def test_scanner_records_missing_source_and_walk_error(tmp_path: Path):
    source = tmp_path / "card"
    source.mkdir()
    good = source / "good.mov"
    bad = source / "bad.mov"
    good.write_bytes(b"ok")
    bad.write_bytes(b"blocked")

    class ReportingFileSystem(FileSystemRepository):
        def walk_with_errors(self, path, on_error=None):
            if on_error:
                on_error(str(source / "locked"), OSError(errno.EACCES, "locked"))
            yield str(source), [], [good.name, bad.name]

        def getsize(self, path: str) -> int:
            if path == str(bad):
                raise OSError(errno.EIO, "entry read failed")
            return super().getsize(path)

    result = scan_sources_unified(
        [str(source), str(tmp_path / "missing")],
        str(tmp_path / "destination"),
        None,
        ReportingFileSystem(),
    )

    assert [item.source_path for item in result.files_list] == [good]
    assert [issue.code for issue in result.issues] == [
        "SCAN_FAILED",
        "SOURCE_UNREADABLE",
        "SOURCE_NOT_FOUND",
    ]
    assert result.issues[0].source_path == str(source / "locked")


def test_completion_serializes_issues_in_registration_order(tmp_path: Path):
    destination = tmp_path / "destination"
    destination.mkdir()
    orchestrator = _orchestrator(destination, create_md_log=False)
    first = create_message_issue(
        stage="scanning",
        code=OperationIssueCode.SCAN_FAILED,
        message="Первая ошибка",
        source_path="/Volumes/CARD",
    )
    second = create_message_issue(
        stage="copy.write_temporary_file",
        code=OperationIssueCode.NO_SPACE_LEFT,
        message="Вторая ошибка",
        destination_path=str(destination / "clip.mov"),
    )
    orchestrator.record_issue(first)
    orchestrator.record_issue(second)
    orchestrator.record_issue(first)

    stats = CompletionService().prepare_completion_stats(orchestrator)

    assert [issue["message"] for issue in stats["issues"]] == [
        "Первая ошибка",
        "Вторая ошибка",
    ]
    assert orchestrator.failed_files == 2
    assert determine_completion_status(stats) is BackupCompletionStatus.FAILED


def test_markdown_contains_safe_ordered_issue_details(tmp_path: Path):
    issue = create_message_issue(
        stage="copy.write_temporary_file",
        code=OperationIssueCode.NO_SPACE_LEFT,
        message="Не удалось *записать* файл\nна диск",
        source_path="/Volumes/CARD/clip`1.mov",
        destination_path="/Volumes/BACKUP/clip.mov",
        file_name="clip.mov",
        technical_message="[Errno 28] No space left\non device",
    )
    logger = BackupLogger()

    path = logger.create_md_log_file(
        destination_root=str(tmp_path),
        source_drives=["/Volumes/CARD"],
        start_time=datetime(2026, 8, 4, 14, 0, 0),
        end_time=datetime(2026, 8, 4, 14, 1, 0),
        total_files=1,
        successful_files=0,
        failed_files=1,
        copied_files={},
        file_system=FileSystemRepository(),
        issues=[issue.to_dict()],
    )

    content = Path(path).read_text(encoding="utf-8")
    assert "## Ошибки" in content
    assert "`clip.mov`" in content
    assert "Источник" in content and "Назначение" in content
    assert "Копирование" in content
    assert "`NO_SPACE_LEFT`" in content
    assert "Техническая информация" in content
    assert "\\*записать\\*" in content
    assert "на диск" in content
    assert "traceback" not in content.lower()


def test_success_markdown_has_no_empty_issue_section(tmp_path: Path):
    path = BackupLogger().create_md_log_file(
        destination_root=str(tmp_path),
        source_drives=[],
        start_time=datetime(2026, 8, 4, 14, 0, 0),
        end_time=datetime(2026, 8, 4, 14, 1, 0),
        total_files=0,
        successful_files=0,
        failed_files=0,
        copied_files={},
        file_system=FileSystemRepository(),
        issues=[],
    )
    assert "## Ошибки" not in Path(path).read_text(encoding="utf-8")


def test_completion_creates_markdown_with_zero_successes_when_issue_exists(
    tmp_path: Path,
):
    destination = tmp_path / "destination"
    destination.mkdir()
    orchestrator = _orchestrator(destination, create_md_log=True)
    orchestrator.record_issue(
        create_message_issue(
            stage="scanning",
            code=OperationIssueCode.SCAN_FAILED,
            message="Источник прочитан не полностью",
            source_path="/Volumes/CARD",
        )
    )

    path = CompletionService().create_md_log_if_needed(orchestrator)

    assert path
    assert Path(path).exists()
    assert "Источник прочитан не полностью" in Path(path).read_text(encoding="utf-8")


def test_fatal_error_creates_best_effort_emergency_markdown(tmp_path: Path):
    destination = tmp_path / "destination"
    destination.mkdir()
    orchestrator = _orchestrator(destination, create_md_log=False)

    try:
        raise RuntimeError("fatal stage failure")
    except RuntimeError as exc:
        orchestrator._handle_error(exc)

    reports = list(destination.glob("backup_log_*.md"))
    assert len(reports) == 1
    content = reports[0].read_text(encoding="utf-8")
    assert "Критическая ошибка" in content
    assert "fatal stage failure" in content
    assert orchestrator.operation_issues[-1].fatal is True


def test_report_write_failure_is_structured_and_does_not_raise(tmp_path: Path):
    class FailingReportFileSystem(FileSystemRepository):
        def open(self, path: str, mode: str, *args, **kwargs):
            if mode == "w":
                raise OSError(errno.ENOSPC, "report disk full")
            return super().open(path, mode, *args, **kwargs)

    logger = BackupLogger()
    result = logger.create_md_log_file(
        destination_root=str(tmp_path),
        source_drives=[],
        start_time=datetime.now(),
        end_time=datetime.now(),
        total_files=0,
        successful_files=0,
        failed_files=1,
        copied_files={},
        file_system=FailingReportFileSystem(),
        issues=[],
    )

    assert result == ""
    assert logger.last_issue is not None
    assert logger.last_issue.code == "NO_SPACE_LEFT"


def test_completion_saves_fallback_markdown_when_destination_rejects_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    destination = tmp_path / "destination"
    destination.mkdir()
    fallback_root = tmp_path / "app-data"

    class FailingDestinationReportFileSystem(FileSystemRepository):
        def open(self, path: str, mode: str, *args, **kwargs):
            if mode == "w" and Path(path).is_relative_to(destination):
                raise OSError(errno.EINVAL, "destination driver rejected write")
            return super().open(path, mode, *args, **kwargs)

    messages: list[str] = []
    orchestrator = _orchestrator(destination, create_md_log=True)
    monkeypatch.setenv("FILM_BACKUP_PRO_APP_DATA_DIR", str(fallback_root))
    orchestrator.file_system = FailingDestinationReportFileSystem()
    orchestrator.log_callback = messages.append
    orchestrator.successful_files = 1
    orchestrator.total_files = 1

    path = CompletionService().create_md_log_if_needed(orchestrator)

    assert path
    assert Path(path).parent == fallback_root / "reports"
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8")
    assert str(destination) in content
    assert "REPORT_WRITE_FAILED" in content
    assert "destination driver rejected write" in content
    assert orchestrator.backup_logger.last_issue is not None
    assert orchestrator.backup_logger.last_issue.code == "REPORT_WRITE_FAILED"
    assert any(str(path) in message for message in messages)


def _orchestrator(destination: Path, *, create_md_log: bool) -> BackupOrchestrator:
    os.environ["FILM_BACKUP_PRO_APP_DATA_DIR"] = str(destination / "app-data")
    return BackupOrchestrator.create(
        run=BackupRunConfig(
            destination_root=str(destination),
            source_drives=[],
            verification_mode="fast",
            create_md_log=create_md_log,
            prevent_sleep=False,
        ),
        tokens=BackupTokens.from_legacy(),
        callbacks=BackupCallbacks(
            log_callback=lambda _message: None,
            progress_callback=None,
            signals=None,
            verification_action_callback=None,
            copy_conflict_action_callback=None,
            success_callback=None,
            progress_batcher=None,
        ),
        deps=BackupDeps(file_system=FileSystemRepository()),
    )
