from __future__ import annotations

import os
from pathlib import Path

from backup_state_manager import BackupStateManager, canonicalize_path
from ui.main_window_controller import canonicalize_path_for_compare


def test_controller_and_state_manager_share_canonicalizer() -> None:
    assert canonicalize_path_for_compare is canonicalize_path
    assert BackupStateManager.canonicalize_path("/tmp/example/") == canonicalize_path(
        "/tmp/example/"
    )


def test_canonicalize_path_for_compare_strips_trailing_slash(tmp_path: Path) -> None:
    p = tmp_path / "proj"
    p.mkdir()
    assert canonicalize_path_for_compare(str(p) + "/") == canonicalize_path_for_compare(str(p))


def test_canonicalize_path_for_compare_normalizes_dotdot(tmp_path: Path) -> None:
    base = tmp_path / "a" / "b"
    base.mkdir(parents=True)
    target = tmp_path / "a" / "c"
    target.mkdir(parents=True)

    p1 = str(tmp_path / "a" / "b" / ".." / "c")
    assert canonicalize_path_for_compare(p1) == canonicalize_path_for_compare(str(target))


def test_canonicalize_path_for_compare_resolves_symlink(tmp_path: Path) -> None:
    real = tmp_path / "realproj"
    real.mkdir()
    link = tmp_path / "linkproj"
    os.symlink(real, link)

    assert canonicalize_path_for_compare(str(link)) == canonicalize_path_for_compare(str(real))
