"""Безопасное извлечение внешних томов-источников на macOS."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class EjectResult:
    volume_path: str
    success: bool
    message: str


def external_volumes_for_sources(source_paths: Iterable[str]) -> list[str]:
    """Возвращает уникальные корни ``/Volumes/<name>`` для путей источников."""
    volumes: list[str] = []
    seen: set[str] = set()

    for source_path in source_paths:
        try:
            resolved = Path(source_path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError):
            continue

        parts = resolved.parts
        if len(parts) < 3 or parts[0] != os.sep or parts[1] != "Volumes":
            continue

        volume_path = str(Path(os.sep, "Volumes", parts[2]))
        if volume_path not in seen:
            seen.add(volume_path)
            volumes.append(volume_path)

    return volumes


def eject_volume(volume_path: str) -> EjectResult:
    """Извлекает один внешний том через ``diskutil eject``."""
    if sys.platform != "darwin":
        return EjectResult(volume_path, False, "Извлечение поддерживается только на macOS")

    normalized = os.path.realpath(volume_path)
    if not normalized.startswith("/Volumes/") or normalized.count(os.sep) != 2:
        return EjectResult(volume_path, False, "Путь не является внешним томом")

    try:
        completed = subprocess.run(
            ["diskutil", "eject", normalized],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return EjectResult(normalized, False, str(error))

    output = (completed.stdout or completed.stderr or "").strip()
    return EjectResult(
        normalized,
        completed.returncode == 0,
        output or ("Том извлечён" if completed.returncode == 0 else "Не удалось извлечь том"),
    )
