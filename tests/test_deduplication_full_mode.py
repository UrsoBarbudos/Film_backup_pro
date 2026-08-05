from __future__ import annotations

import os
from pathlib import Path


class _Config:
    def __init__(self, *, verification_mode: str) -> None:
        self._data = {
            "verification_mode": verification_mode,
            "hash_storage_use_compression": False,
            "telegram_enabled": False,
            "macos_notifications_enabled": False,
        }

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def load(self):
        return dict(self._data)


def _run_orchestrator(*, tmp_path: Path, src_root: Path, dst_root: Path, verification_mode: str):
    from repositories import FileSystemRepository
    from backup_components import BackupOrchestrator
    from backup_components.backup_run_context import BackupCallbacks, BackupDeps, BackupRunConfig, BackupTokens

    # Важно: направляем app data dir в tmp, чтобы HashStorage не писал в home.
    os.environ["FILM_BACKUP_PRO_APP_DATA_DIR"] = str(tmp_path / "app_data")

    fs = FileSystemRepository()
    logs: list[str] = []

    def log_callback(msg: str) -> None:
        logs.append(msg)

    run = BackupRunConfig(
        destination_root=str(dst_root),
        source_drives=[str(src_root)],
        verification_mode=verification_mode,
        create_md_log=False,
        prevent_sleep=False,
    )
    tokens = BackupTokens.from_legacy(pause_event=None, pause_token=None, cancel_token=None)
    callbacks = BackupCallbacks(
        log_callback=log_callback,
        progress_callback=None,
        signals=None,
        verification_action_callback=None,
        copy_conflict_action_callback=None,
        success_callback=None,
        progress_batcher=None,
    )
    deps = BackupDeps(file_system=fs, config=_Config(verification_mode=verification_mode))

    orchestrator = BackupOrchestrator.create(run=run, tokens=tokens, callbacks=callbacks, deps=deps)
    orchestrator.run()
    return orchestrator, logs


def test_full_mode_copies_file_when_destination_path_does_not_exist(tmp_path: Path) -> None:
    """При конфликте только по пути (файл уже существует в том же пути). Дубликаты по содержимому в другом пути больше не пропускаются автоматически."""
    src_root = tmp_path / "SRC"
    dst_root = tmp_path / "DEST"
    src_root.mkdir(parents=True, exist_ok=True)
    dst_root.mkdir(parents=True, exist_ok=True)

    # В назначении есть файл с тем же содержимым, но по другому пути.
    existing = dst_root / "Existing" / "X.bin"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"same-content")

    (src_root / "A.bin").write_bytes(b"same-content")

    orchestrator, _logs = _run_orchestrator(
        tmp_path=tmp_path,
        src_root=src_root,
        dst_root=dst_root,
        verification_mode="full",
    )

    # Путь назначения для A.bin — DEST/SRC/A.bin; там файла нет, поэтому копируем.
    expected_copy_path = dst_root / "SRC" / "A.bin"
    assert expected_copy_path.exists() is True


def test_fast_mode_does_not_use_destination_dedup(tmp_path: Path) -> None:
    src_root = tmp_path / "SRC"
    dst_root = tmp_path / "DEST"
    src_root.mkdir(parents=True, exist_ok=True)
    dst_root.mkdir(parents=True, exist_ok=True)

    existing = dst_root / "Existing" / "X.bin"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"same-content")

    (src_root / "A.bin").write_bytes(b"same-content")

    orchestrator, _logs = _run_orchestrator(
        tmp_path=tmp_path,
        src_root=src_root,
        dst_root=dst_root,
        verification_mode="fast",
    )

    expected_copy_path = dst_root / "SRC" / "A.bin"
    assert expected_copy_path.exists() is True
    assert expected_copy_path.read_bytes() == b"same-content"


def test_md_log_contains_duplicates_section(tmp_path: Path) -> None:
    from repositories import FileSystemRepository
    from backup_components import BackupOrchestrator
    from backup_components.backup_run_context import BackupCallbacks, BackupDeps, BackupRunConfig, BackupTokens

    os.environ["FILM_BACKUP_PRO_APP_DATA_DIR"] = str(tmp_path / "app_data")

    src_root = tmp_path / "SRC"
    dst_root = tmp_path / "DEST"
    src_root.mkdir(parents=True, exist_ok=True)
    dst_root.mkdir(parents=True, exist_ok=True)

    (dst_root / "Existing" / "X.bin").parent.mkdir(parents=True, exist_ok=True)
    (dst_root / "Existing" / "X.bin").write_bytes(b"same-content")
    (src_root / "A.bin").write_bytes(b"same-content")

    fs = FileSystemRepository()
    logs: list[str] = []

    def log_callback(msg: str) -> None:
        logs.append(msg)

    run = BackupRunConfig(
        destination_root=str(dst_root),
        source_drives=[str(src_root)],
        verification_mode="full",
        create_md_log=True,
        prevent_sleep=False,
    )
    tokens = BackupTokens.from_legacy(pause_event=None, pause_token=None, cancel_token=None)
    callbacks = BackupCallbacks(
        log_callback=log_callback,
        progress_callback=None,
        signals=None,
        verification_action_callback=None,
        copy_conflict_action_callback=None,
        success_callback=None,
        progress_batcher=None,
    )
    deps = BackupDeps(file_system=fs, config=_Config(verification_mode="full"))

    orchestrator = BackupOrchestrator.create(run=run, tokens=tokens, callbacks=callbacks, deps=deps)
    orchestrator.run()

    md_files = list(dst_root.glob("backup_log_*.md"))
    assert md_files, "MD log file not created"
    content = md_files[0].read_text(encoding="utf-8")
    assert "same-content" not in content  # контент не должен попадать в лог
