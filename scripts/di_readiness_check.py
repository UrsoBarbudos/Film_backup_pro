"""
Readiness-check DI: убедиться, что в коде нет импортов из factories (модуль удалён).
Контрактная проверка (не часть пользовательского функционала).

Запуск:
    .venv/bin/python scripts/di_readiness_check.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {".venv", ".cursor", "__pycache__", ".git", "scripts"}

PATTERN = re.compile(r"^\s*from\s+factories\s+import\s+", re.MULTILINE)


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # фильтруем директории на месте (чтобы os.walk не заходил)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = Path(dirpath) / name
            files.append(path)
    return sorted(files)


def main() -> int:
    offenders: list[tuple[Path, int]] = []

    for path in iter_python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = list(PATTERN.finditer(text))
        if matches:
            offenders.append((path.relative_to(ROOT), len(matches)))

    if offenders:
        print("FAIL: обнаружены импорты из factories (модуль удалён):")
        for path, count in offenders:
            print(f"- {path} (matches={count})")
        return 2

    print("OK: импорты из factories отсутствуют")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

