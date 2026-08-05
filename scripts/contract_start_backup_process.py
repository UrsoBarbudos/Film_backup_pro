"""
Контрактные проверки для публичного API запуска бэкапа.
Контрактная проверка (не часть пользовательского функционала).

Задача: удержать стабильность при рефакторинге.

Запуск:
    .venv/bin/python scripts/contract_start_backup_process.py
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path


def _require_param_default(sig: inspect.Signature, name: str, expected_default) -> None:
    if name not in sig.parameters:
        raise AssertionError(f"Missing parameter: {name}")
    param = sig.parameters[name]
    if param.default != expected_default:
        raise AssertionError(f"Unexpected default for {name}: {param.default!r} (expected {expected_default!r})")


def main() -> int:
    # Обеспечиваем импорт модулей проекта при запуске как скрипта из /scripts
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import engine
    from engine_modules import entrypoints

    # 1) Импорт/реэкспорт не должен ломаться
    assert hasattr(engine, "start_backup_process"), "engine.start_backup_process is missing"
    assert engine.start_backup_process is entrypoints.start_backup_process, (
        "engine.start_backup_process must be a thin re-export of engine_modules.entrypoints.start_backup_process"
    )

    # 2) Сигнатура и ключевые дефолты не должны «случайно» меняться
    sig = inspect.signature(engine.start_backup_process)
    _require_param_default(sig, "file_system", None)
    assert "simple_copy_mode" not in sig.parameters
    assert "project_name" not in sig.parameters
    _require_param_default(sig, "create_md_log", False)
    _require_param_default(sig, "prevent_sleep", True)

    # 3) Ожидаемое поведение при отсутствии обязательной зависимости (FS)
    # В текущей архитектуре BackupOrchestrator требует file_system явно.
    try:
        engine.start_backup_process(
            destination_root="/tmp",
            source_drives=[],
            log_callback=lambda _msg: None,
            file_system=None,
        )
    except Exception as exc:  # noqa: BLE001 - контракт фиксирует тип/сообщение исключения
        assert isinstance(exc, ValueError), f"Expected ValueError for missing file_system, got {type(exc)}: {exc}"
        msg = str(exc)
        assert "file_system must be provided" in msg, f"Unexpected error message: {msg!r}"
    else:
        raise AssertionError("Expected start_backup_process() to fail when file_system is None")

    print("CONTRACT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
