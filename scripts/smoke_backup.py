from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# При запуске `python scripts/smoke_backup.py` sys.path[0] указывает на папку `scripts/`,
# поэтому добавляем корень проекта, чтобы импортировать `engine.py` как модуль `engine`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engine import start_backup_process
from repositories import FileSystemRepository


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class SmokeConfig:
    """
    Минимальная конфигурация для smoke-теста.

    BackupOrchestrator/BackupNotifier ожидают интерфейс с `.get()` и `.load()`,
    поэтому используем простой адаптер без обращения к диску.
    """

    def __init__(self, *, verification_mode: str) -> None:
        self._data = {
            "verification_mode": verification_mode,
            "telegram_enabled": False,
            "macos_notifications_enabled": False,
        }

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def load(self):
        return dict(self._data)


def main() -> int:
    fs = FileSystemRepository()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src_root = root / "SRC"
        dst_root_simple = root / "DEST_SIMPLE"
        dst_root_verify = root / "DEST_VERIFY"
        # Важно для запуска в sandbox/CI: направляем app data dir в папку внутри проекта,
        # чтобы HashStorage не пытался писать в ~/Library/... и чтобы директория пережила atexit().
        smoke_app_data = PROJECT_ROOT / ".smoke_app_data"
        smoke_app_data.mkdir(parents=True, exist_ok=True)
        os.environ["FILM_BACKUP_PRO_APP_DATA_DIR"] = str(smoke_app_data)
        src_root.mkdir(parents=True, exist_ok=True)
        dst_root_simple.mkdir(parents=True, exist_ok=True)
        dst_root_verify.mkdir(parents=True, exist_ok=True)

        _write_file(src_root / "A.txt", b"hello")
        _write_file(src_root / "nested" / "B.bin", b"\x00\x01\x02\x03")
        _write_file(src_root / "nested" / "deep" / "C.txt", b"world")

        def run_case(*, dst_root: Path, config: SmokeConfig) -> list[str]:
            logs: list[str] = []

            def log_callback(msg: str) -> None:
                logs.append(msg)

            # Важно: в приложении file_system передаётся из composition root и обязателен для BackupOrchestrator.
            start_backup_process(
                destination_root=str(dst_root),
                source_drives=[str(src_root)],
                log_callback=log_callback,
                prevent_sleep=False,
                create_md_log=False,
                config=config,
                file_system=fs,
            )

            return logs

        def assert_files_ok(dst_root: Path, logs: list[str]) -> int:
            if not any("Назначение:" in line for line in logs):
                print('SMOKE FAILED: missing destination log marker')
                for line in logs[-50:]:
                    print(line)
                return 1

            # Единственный режим не должен создавать проектную структуру.
            forbidden_dirs = [
                dst_root / "Footage",
                dst_root / "Sound",
                dst_root / "Photo",
            ]
            for d in forbidden_dirs:
                if d.exists():
                    print("SMOKE FAILED: unexpected project-structure directory:", d)
                    return 1

            expected = [
                dst_root / "SRC" / "A.txt",
                dst_root / "SRC" / "nested" / "B.bin",
                dst_root / "SRC" / "nested" / "deep" / "C.txt",
            ]
            for p in expected:
                if not p.exists():
                    print("SMOKE FAILED: missing file:", p)
                    for line in logs[-30:]:
                        print(line)
                    return 1

            if (dst_root / "SRC" / "A.txt").read_bytes() != b"hello":
                print("SMOKE FAILED: content mismatch for A.txt")
                return 1

            if (dst_root / "SRC" / "nested" / "B.bin").read_bytes() != b"\x00\x01\x02\x03":
                print("SMOKE FAILED: content mismatch for B.bin")
                return 1

            if (dst_root / "SRC" / "nested" / "deep" / "C.txt").read_bytes() != b"world":
                print("SMOKE FAILED: content mismatch for C.txt")
                return 1

            return 0

        logs_verify = run_case(
            dst_root=dst_root_verify,
            config=SmokeConfig(verification_mode="fast"),
        )

        if not any("Этап 2: Проверка" in line for line in logs_verify):
            print('SMOKE FAILED: missing verification stage marker ("Этап 2: Проверка")')
            for line in logs_verify[-80:]:
                print(line)
            return 1

        rc = assert_files_ok(dst_root_verify, logs_verify)
        if rc != 0:
            return rc

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
