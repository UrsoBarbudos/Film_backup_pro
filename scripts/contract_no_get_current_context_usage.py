"""
Контракт: `get_current_context()` допускается только в allowlist.
Контрактная проверка (не часть пользовательского функционала).

Зачем: сжать service-locator до явного переходного слоя и убрать hidden-deps из core.

Запуск:
    .venv/bin/python scripts/contract_no_get_current_context_usage.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ALLOWLIST = {
    "composition.py",
}


def _is_ignored(path: Path) -> bool:
    # Не проверяем сам контрактный скрипт (он по определению содержит паттерн/слово).
    if path.name == "contract_no_get_current_context_usage.py":
        return True

    # Игнорируем скрытые/служебные директории и артефакты.
    ignored_dirnames = {
        ".venv",
        "venv",
        "__pycache__",
        ".cursor",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
    }
    for part in path.parts:
        if part in ignored_dirnames:
            return True
        if part.startswith(".") and part not in {".", ".."}:
            return True
    return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    needle = re.compile(r"\bget_current_context\s*\(")
    violations: list[str] = []

    for py_file in root.rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        if _is_ignored(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            # best-effort: не заваливаем контракт из-за проблем чтения редких файлов
            continue

        if not needle.search(content):
            continue

        if rel not in ALLOWLIST:
            violations.append(rel)

    if violations:
        print("CONTRACT FAILED: запрещённые вызовы get_current_context() обнаружены в файлах:")
        for rel in sorted(violations):
            print(" -", rel)
        print("\nРазрешено только:", ", ".join(sorted(ALLOWLIST)))
        return 2

    print("CONTRACT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

