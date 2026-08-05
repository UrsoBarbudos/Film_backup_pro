"""
Контракт: финализация DI (Фаза 4).
Контрактная проверка (не часть пользовательского функционала).

Проверяет, что legacy fallback отключены:
- resolve_file_system(None) падает
- SourceManager требует file_system явно

Запуск:
    .venv/bin/python scripts/contract_phase4_finalization.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from utils import resolve_file_system

    # 1) resolve_file_system(None) должен падать
    try:
        resolve_file_system(None)
    except Exception as exc:  # noqa: BLE001 - контракт фиксирует поведение
        if not isinstance(exc, ValueError):
            print("CONTRACT FAILED: resolve_file_system(None) expected ValueError, got:", type(exc), exc)
            return 2
    else:
        print("CONTRACT FAILED: resolve_file_system(None) must raise")
        return 2

    # 2) SourceManager должен требовать file_system явно
    from source_manager import SourceManager

    try:
        _ = SourceManager()  # type: ignore[call-arg]
    except TypeError:
        pass
    except Exception as exc:  # noqa: BLE001
        print("CONTRACT FAILED: SourceManager() expected TypeError, got:", type(exc), exc)
        return 2
    else:
        print("CONTRACT FAILED: SourceManager() must not be callable without file_system")
        return 2

    print("CONTRACT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

