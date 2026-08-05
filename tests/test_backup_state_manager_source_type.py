from __future__ import annotations

from pathlib import Path

from backup_state_manager import BackupStateManager


def test_set_and_get_source_type_with_path_canonicalization(tmp_path: Path) -> None:
    state = BackupStateManager()
    source = tmp_path / "source_a"
    source.mkdir()

    state.add_source_path(str(source))
    updated = state.set_source_type(str(source) + "/", "video")

    assert updated is True
    assert state.get_source_type(str(source)) == "video"


def test_remove_source_path_removes_override_for_canonical_path(tmp_path: Path) -> None:
    state = BackupStateManager()
    source = tmp_path / "source_b"
    source.mkdir()

    state.add_source_path(str(source))
    state.set_source_type(str(source), "audio")

    removed = state.remove_source_path(str(source) + "/")

    assert removed is True
    assert state.has_sources() is False
    assert state.get_source_type(str(source)) is None
