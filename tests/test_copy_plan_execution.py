from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine_modules.scanning as scanning_module
from backup_components.exceptions import BackupCancelledError
from backup_components.file_copier import FileCopier
from backup_components.operation_results import CopyResult
from backup_components.orchestrator_services.copy_plan_and_execute_service import (
    CopyPlanAndExecuteService,
)
from backup_components.orchestrator_services.completion_service import CompletionService
from backup_components.orchestrator_services.progress_reporting_service import (
    ProgressReportingService,
)
from backup_components.completion_status import BackupCompletionStatus, determine_completion_status
from engine_modules.category_definitions import CATEGORY_DEFINITIONS
from engine_modules.scanning import PlannedCopy, scan_sources_unified
from repositories.file_system_repository import FileSystemRepository


class CountingFileSystem(FileSystemRepository):
    def __init__(self) -> None:
        self.walk_calls = 0
        self.relpath_calls = 0

    def walk(self, path: str):
        self.walk_calls += 1
        yield from super().walk(path)

    def relpath(self, path: str, start: str) -> str:
        self.relpath_calls += 1
        return super().relpath(path, start)


class RecordingCopier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def copy_file(
        self,
        source_path,
        destination_path,
        destination_root=None,
        progress_callback=None,
        base_copied_bytes=0,
        total_bytes=0,
    ):
        Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        self.calls.append((source_path, destination_path))
        return CopyResult(success=True, copied_size=Path(source_path).stat().st_size)


def make_orchestrator(tmp_path: Path, plan: list[PlannedCopy], fs=None):
    destination = tmp_path / "destination"
    destination.mkdir(exist_ok=True)
    copier = RecordingCopier()
    logs: list[str] = []
    orchestrator = SimpleNamespace(
        all_files_to_copy=plan,
        scan_result=SimpleNamespace(files_list=plan),
        source_drives=[],
        destination_root=str(destination),
        file_system=fs or CountingFileSystem(),
        file_copier=copier,
        log_callback=logs.append,
        copy_conflict_policy=None,
        copy_conflict_action_callback=None,
        cancel_token=None,
        progress_batcher=None,
        progress_callback=None,
        copied_bytes=0,
        last_copied_bytes=0,
        total_bytes=0,
        total_files=0,
        successful_files=0,
        failed_files=0,
        skipped_files=0,
        skipped_bytes=0,
        copy_plan_completed=False,
        current_file="",
        files_to_verify=[],
        create_md_log=False,
        copied_files={definition.key: [] for definition in CATEGORY_DEFINITIONS},
        signals=None,
        _check_cancellation=lambda: None,
        _check_pause=lambda: None,
        _update_progress=lambda: None,
    )
    return orchestrator, copier, logs


def scan(source_paths: list[Path], destination: Path, fs: CountingFileSystem):
    return scan_sources_unified(
        [str(path) for path in source_paths],
        str(destination),
        None,
        fs,
    )


def test_execution_uses_exact_plan_without_second_walk_or_relpath(tmp_path: Path) -> None:
    source = tmp_path / "card"
    (source / "nested").mkdir(parents=True)
    (source / "a.mov").write_bytes(b"aaa")
    (source / "nested" / "b.jpg").write_bytes(b"bb")
    fs = CountingFileSystem()
    result = scan([source], tmp_path / "destination", fs)
    scanned_walks = fs.walk_calls
    scanned_relpaths = fs.relpath_calls
    orchestrator, copier, _ = make_orchestrator(tmp_path, result.files_list, fs)

    CopyPlanAndExecuteService().copy_all_files(orchestrator)

    assert fs.walk_calls == scanned_walks
    assert fs.relpath_calls == scanned_relpaths
    assert {Path(src).name for src, _ in copier.calls} == {"a.mov", "b.jpg"}
    assert {
        Path(dst).relative_to(orchestrator.destination_root)
        for _, dst in copier.calls
    } == {item.relative_path for item in result.files_list}
    assert orchestrator.total_files == len(result.files_list) == 2
    assert orchestrator.total_bytes == sum(item.size for item in result.files_list) == 5


def test_validation_does_not_open_source_before_copy_file(tmp_path: Path) -> None:
    class SourceOpenCountingFileSystem(CountingFileSystem):
        def __init__(self) -> None:
            super().__init__()
            self.source_read_opens = 0

        def open(self, path: str, mode: str, *args, **kwargs):
            if mode == "rb" and Path(path) == source / "clip.mov":
                self.source_read_opens += 1
            return super().open(path, mode, *args, **kwargs)

    source = tmp_path / "card"
    source.mkdir()
    (source / "clip.mov").write_bytes(b"data")
    fs = SourceOpenCountingFileSystem()
    result = scan([source], tmp_path / "destination", fs)
    orchestrator, _, _ = make_orchestrator(tmp_path, result.files_list, fs)
    orchestrator.file_copier = FileCopier(file_system=fs, verification_mode="full")

    CopyPlanAndExecuteService().copy_all_files(orchestrator)

    assert fs.source_read_opens == 1


@pytest.mark.parametrize("mutation", ["change", "delete"])
def test_changed_or_deleted_file_is_controlled_error(tmp_path: Path, mutation: str) -> None:
    source = tmp_path / "card"
    source.mkdir()
    media = source / "clip.mov"
    media.write_bytes(b"old")
    fs = CountingFileSystem()
    result = scan([source], tmp_path / "destination", fs)
    orchestrator, copier, logs = make_orchestrator(tmp_path, result.files_list, fs)
    if mutation == "change":
        media.write_bytes(b"new-content")
    else:
        media.unlink()

    CopyPlanAndExecuteService().copy_all_files(orchestrator)

    assert copier.calls == []
    assert orchestrator.failed_files == 1
    assert any(
        ("изменён после сканирования" if mutation == "change" else "удалён после сканирования")
        in message
        for message in logs
    )


def test_new_file_and_excluded_files_are_not_added_during_execution(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "card"
    source.mkdir()
    (source / "planned.mov").write_bytes(b"data")
    (source / ".DS_Store").write_bytes(b"ignored")
    fs = CountingFileSystem()
    system_checks = 0
    category_checks = 0
    original_is_system_file = scanning_module.is_system_file
    original_get_file_category = scanning_module.get_file_category

    def count_system_check(filename: str) -> bool:
        nonlocal system_checks
        system_checks += 1
        return original_is_system_file(filename)

    def count_category_check(filename: str) -> str:
        nonlocal category_checks
        category_checks += 1
        return original_get_file_category(filename)

    monkeypatch.setattr(scanning_module, "is_system_file", count_system_check)
    monkeypatch.setattr(scanning_module, "get_file_category", count_category_check)
    result = scan([source], tmp_path / "destination", fs)
    checks_after_scan = (system_checks, category_checks)
    (source / "late.mov").write_bytes(b"late")
    orchestrator, copier, _ = make_orchestrator(tmp_path, result.files_list, fs)

    CopyPlanAndExecuteService().copy_all_files(orchestrator)

    assert [Path(src).name for src, _ in copier.calls] == ["planned.mov"]
    assert [item.source_path.name for item in result.files_list] == ["planned.mov"]
    assert (system_checks, category_checks) == checks_after_scan


def test_multiple_same_named_sources_have_distinct_planned_paths(tmp_path: Path) -> None:
    first = tmp_path / "one" / "card"
    second = tmp_path / "two" / "card"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "clip.mov").write_bytes(b"one")
    (second / "clip.mov").write_bytes(b"two")
    fs = CountingFileSystem()

    result = scan([first, second], tmp_path / "destination", fs)

    relative_paths = [item.relative_path for item in result.files_list]
    assert relative_paths == [Path("card/clip.mov"), Path("card_2/clip.mov")]
    assert len(set(relative_paths)) == 2


def test_real_suffixed_source_name_is_not_taken_by_duplicate_suffix(tmp_path: Path) -> None:
    sources = [
        tmp_path / "one" / "card",
        tmp_path / "two" / "card",
        tmp_path / "three" / "card_2",
    ]
    for index, source in enumerate(sources):
        source.mkdir(parents=True)
        (source / f"{index}.mov").write_bytes(b"x")

    result = scan(sources, tmp_path / "destination", CountingFileSystem())

    assert [item.relative_path.parts[0] for item in result.files_list] == [
        "card",
        "card_3",
        "card_2",
    ]


def test_three_same_named_sources_receive_unique_roots(tmp_path: Path) -> None:
    sources = [tmp_path / str(index) / "card" for index in range(3)]
    for index, source in enumerate(sources):
        source.mkdir(parents=True)
        (source / f"{index}.mov").write_bytes(b"x")

    result = scan(sources, tmp_path / "destination", CountingFileSystem())

    assert [item.relative_path.parts[0] for item in result.files_list] == [
        "card",
        "card_2",
        "card_3",
    ]


def test_single_file_and_directory_with_same_name_do_not_collide(tmp_path: Path) -> None:
    single_file = tmp_path / "single" / "card"
    directory = tmp_path / "directory" / "card"
    single_file.parent.mkdir()
    single_file.write_bytes(b"single")
    directory.mkdir(parents=True)
    (directory / "clip.mov").write_bytes(b"directory")

    result = scan(
        [single_file, directory],
        tmp_path / "destination",
        CountingFileSystem(),
    )

    assert [item.relative_path for item in result.files_list] == [
        Path("card"),
        Path("card_2/clip.mov"),
    ]


def test_existing_destination_symlink_cannot_escape_root(tmp_path: Path) -> None:
    source = tmp_path / "card"
    source.mkdir()
    media = source / "clip.mov"
    media.write_bytes(b"data")
    destination = tmp_path / "destination"
    outside = tmp_path / "outside"
    destination.mkdir()
    outside.mkdir()
    (destination / "card").symlink_to(outside, target_is_directory=True)
    fs = CountingFileSystem()
    result = scan([source], destination, fs)
    orchestrator, copier, logs = make_orchestrator(tmp_path, result.files_list, fs)

    CopyPlanAndExecuteService().copy_all_files(orchestrator)

    assert copier.calls == []
    assert orchestrator.failed_files == 1
    assert not (outside / "clip.mov").exists()
    assert sum("выходит за пределы" in message.lower() for message in logs) == 1


@pytest.mark.parametrize("action", ["skip", "replace"])
def test_conflict_progress_and_required_size_follow_executed_plan(
    tmp_path: Path, action: str
) -> None:
    source = tmp_path / "card"
    source.mkdir()
    media = source / "clip.mov"
    media.write_bytes(b"new")
    fs = CountingFileSystem()
    result = scan([source], tmp_path / "destination", fs)
    orchestrator, copier, _ = make_orchestrator(tmp_path, result.files_list, fs)
    destination_file = Path(orchestrator.destination_root) / result.files_list[0].relative_path
    destination_file.parent.mkdir(parents=True)
    destination_file.write_bytes(b"old")
    progress_updates: list[int] = []
    orchestrator.progress_callback = (
        lambda percent, *_args: progress_updates.append(percent)
    )
    progress_service = ProgressReportingService()
    orchestrator._update_progress = lambda: progress_service.update_progress(orchestrator)
    orchestrator.last_update_time = datetime.now()
    orchestrator.last_copied_bytes = 0
    orchestrator.copy_conflict_action_callback = lambda *_args: (action, False)

    CopyPlanAndExecuteService().copy_all_files(orchestrator)

    assert progress_updates[-1] == 100
    if action == "skip":
        assert copier.calls == []
        assert orchestrator.total_bytes == 0
        assert destination_file.read_bytes() == b"old"
    else:
        assert len(copier.calls) == 1
        assert orchestrator.total_bytes == len(b"new")
        assert destination_file.read_bytes() == b"new"


def test_cancellation_while_resolving_conflict_stops_execution(tmp_path: Path) -> None:
    source = tmp_path / "card"
    source.mkdir()
    (source / "clip.mov").write_bytes(b"new")
    fs = CountingFileSystem()
    result = scan([source], tmp_path / "destination", fs)
    orchestrator, copier, _ = make_orchestrator(tmp_path, result.files_list, fs)
    destination_file = Path(orchestrator.destination_root) / result.files_list[0].relative_path
    destination_file.parent.mkdir(parents=True)
    destination_file.write_bytes(b"old")

    cancelled = False

    def cancel_from_dialog(*_args):
        nonlocal cancelled
        cancelled = True
        return ("skip", False)

    def check_cancellation() -> None:
        if cancelled:
            raise BackupCancelledError()

    orchestrator.copy_conflict_action_callback = cancel_from_dialog
    orchestrator._check_cancellation = check_cancellation

    with pytest.raises(BackupCancelledError):
        CopyPlanAndExecuteService().copy_all_files(orchestrator)

    assert copier.calls == []
    assert orchestrator.copy_plan_completed is False
    assert destination_file.read_bytes() == b"old"


def test_validation_failure_is_counted_once_and_prevents_success_status(
    tmp_path: Path,
) -> None:
    source = tmp_path / "card"
    source.mkdir()
    media = source / "clip.mov"
    media.write_bytes(b"planned")
    fs = CountingFileSystem()
    result = scan([source], tmp_path / "destination", fs)
    media.unlink()
    orchestrator, copier, logs = make_orchestrator(tmp_path, result.files_list, fs)

    CopyPlanAndExecuteService().copy_all_files(orchestrator)
    stats = CompletionService().prepare_completion_stats(orchestrator)

    assert copier.calls == []
    assert orchestrator.failed_files == 1
    assert sum(message.startswith("❌ Файл clip.mov") for message in logs) == 1
    assert determine_completion_status(stats) is not BackupCompletionStatus.SUCCESS


def test_cancellation_stops_plan_iteration(tmp_path: Path) -> None:
    source = tmp_path / "card"
    source.mkdir()
    for name in ("a.mov", "b.mov", "c.mov"):
        (source / name).write_bytes(name.encode())
    fs = CountingFileSystem()
    result = scan([source], tmp_path / "destination", fs)
    orchestrator, copier, _ = make_orchestrator(tmp_path, result.files_list, fs)
    checks = 0

    def check_cancellation() -> None:
        nonlocal checks
        checks += 1
        if checks > 1:
            raise BackupCancelledError()

    orchestrator._check_cancellation = check_cancellation

    with pytest.raises(BackupCancelledError):
        CopyPlanAndExecuteService().copy_all_files(orchestrator)

    assert len(copier.calls) == 1
