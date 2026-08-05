"""
Smoke-проверка DI/composition root.
Контрактная проверка (не часть пользовательского функционала).

Запуск:
    .venv/bin/python scripts/di_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Обеспечиваем импорт модулей проекта при запуске как скрипта из /scripts
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from composition import build_test_context, require_current_context

    ctx = build_test_context()
    assert ctx.config is not None
    assert ctx.file_system is not None
    assert ctx.debug_logger is not None

    # Проверяем, что горячие компоненты строятся с явной передачей зависимостей.
    from backup_components.file_copier import FileCopier
    from backup_components.file_verifier import FileVerifier

    _ = FileCopier(file_system=ctx.file_system)
    _ = FileVerifier(file_system=ctx.file_system)

    # BackupOrchestrator должен требовать file_system явно.
    from backup_components.backup_orchestrator import BackupOrchestrator

    _ = BackupOrchestrator(
        destination_root="/tmp",
        source_drives=[],
        log_callback=lambda _msg: None,
        config=ctx.config,
        file_system=ctx.file_system,
    )

    # Убедимся, что context реально установлен.
    assert require_current_context() is ctx

    print("OK: DI smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
