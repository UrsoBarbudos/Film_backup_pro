"""
Единая точка запуска smoke/contract проверок (Safety Net для рефакторинга).
Не бизнес-функция приложения.

Запуск:
    .venv/bin/python scripts/smoke_all.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(script_path: Path) -> int:
    proc = subprocess.run([sys.executable, str(script_path)], check=False)
    return int(proc.returncode)


def main() -> int:
    scripts_dir = Path(__file__).resolve().parent
    repository_root = scripts_dir.parent
    smoke_app_data = repository_root / ".smoke_app_data"
    os.environ["FILM_BACKUP_PRO_APP_DATA_DIR"] = str(smoke_app_data)

    suite = [
        scripts_dir / "di_smoke.py",
        scripts_dir / "contract_no_get_current_context_usage.py",
        scripts_dir / "contract_start_backup_process.py",
        scripts_dir / "smoke_backup.py",
    ]

    for script in suite:
        if not script.exists():
            print("SMOKE_ALL FAILED: missing script:", script)
            return 2

        print(f"==> running: {script.name}")
        code = _run(script)
        if code != 0:
            print(f"SMOKE_ALL FAILED: {script.name} exited with {code}")
            return code

    # Чистим после успешного прогона: процесс smoke_backup уже завершился (atexit отработал).
    try:
        if smoke_app_data.exists():
            for p in sorted(smoke_app_data.glob("**/*"), reverse=True):
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            smoke_app_data.rmdir()
    except Exception:
        # Не падаем из-за уборки мусора
        pass

    print("SMOKE_ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
