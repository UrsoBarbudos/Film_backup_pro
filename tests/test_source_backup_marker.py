import logging
from datetime import datetime, timezone
from pathlib import Path

from engine_modules.scanning import scan_sources_unified
from repositories import FileSystemRepository
from source_backup_marker import SourceBackupMarkerService


def _write_marker(path: Path, verified_at: str) -> None:
    path.write_text(
        "---\n"
        "schema_version: 1\n"
        f'verified_at: "{verified_at}"\n'
        'destination_path: "/Volumes/Backup SSD/Project"\n'
        "source_file_count: 10\n"
        "source_total_bytes: 2048\n"
        "---\n\n# Отметка\n",
        encoding="utf-8",
    )


def test_marker_name_uses_local_date_and_time(tmp_path: Path) -> None:
    service = SourceBackupMarkerService()
    moment = datetime(2026, 7, 27, 10, 30, tzinfo=timezone.utc)
    path = service.write_marker(tmp_path.as_posix(), verified_at=moment, metadata={})
    assert Path(path).name == "DUBLER_BACKUP_27.07.26_1030.md"
    assert 'verified_at: "2026-07-27T10:30:00+00:00"' in Path(path).read_text(
        encoding="utf-8"
    )


def test_two_backups_in_same_minute_keep_both(tmp_path: Path) -> None:
    service = SourceBackupMarkerService()
    first = datetime(2026, 7, 27, 10, 30, 1, tzinfo=timezone.utc)
    second = datetime(2026, 7, 27, 10, 30, 42, tzinfo=timezone.utc)
    first_path = service.write_marker(tmp_path.as_posix(), verified_at=first, metadata={})
    second_path = service.write_marker(tmp_path.as_posix(), verified_at=second, metadata={})
    assert Path(first_path).name == "DUBLER_BACKUP_27.07.26_1030.md"
    assert Path(second_path).name == "DUBLER_BACKUP_27.07.26_1030_42.md"
    assert Path(first_path).exists()


def test_session_suffix_resolves_remaining_name_conflict(tmp_path: Path) -> None:
    service = SourceBackupMarkerService()
    moment = datetime(2026, 7, 27, 10, 30, 42, tzinfo=timezone.utc)
    (tmp_path / "DUBLER_BACKUP_27.07.26_1030.md").touch()
    (tmp_path / "DUBLER_BACKUP_27.07.26_1030_42.md").touch()
    path = service.write_marker(
        tmp_path.as_posix(),
        verified_at=moment,
        metadata={},
        session_id="abcd1234",
    )
    assert Path(path).name == "DUBLER_BACKUP_27.07.26_1030_42_abcd1234.md"


def test_latest_valid_marker_wins_when_newer_named_marker_is_broken(
    tmp_path: Path, caplog
) -> None:
    _write_marker(
        tmp_path / ".DUBLER_BACKUP_26.07.26_1200.md",
        "2026-07-26T12:00:00+03:00",
    )
    _write_marker(
        tmp_path / "DUBLER_BACKUP_27.07.26_0900.md",
        "2026-07-27T09:00:00+03:00",
    )
    (tmp_path / "DUBLER_BACKUP_28.07.26_1000.md").write_text(
        "---\nschema_version: 1\nverified_at: broken\n---\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        marker = SourceBackupMarkerService().read_latest_from_volume(tmp_path.as_posix())
    assert marker is not None
    assert marker.destination_path == "/Volumes/Backup SSD/Project"
    assert "Повреждённая или неподдерживаемая отметка" in caplog.text


def test_all_marker_files_are_excluded_from_scan(tmp_path: Path) -> None:
    source = tmp_path / "source"
    project = tmp_path / "project"
    source.mkdir()
    project.mkdir()
    (source / "clip.mov").write_bytes(b"media")
    _write_marker(
        source / "DUBLER_BACKUP_27.07.26_1030.md",
        "2026-07-27T10:30:00+03:00",
    )
    (source / "DUBLER_BACKUP_27.07.26_1030_42.md.tmp-abcd1234").write_text(
        "temporary", encoding="utf-8"
    )
    result = scan_sources_unified(
        [source.as_posix()],
        project.as_posix(),
        None,
        FileSystemRepository(),
    )
    assert result.total_files == 1
    assert result.total_size == len(b"media")
    assert [item.source_path.name for item in result.files_list] == ["clip.mov"]
