"""
Единая инфраструктура логирования на базе стандартного `logging`.

Фаза A (План 6, базовая часть): единый предсказуемый runtime-лог, уровни,
возможность выключать/настраивать, без прямых записей в файлы из домена.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class LoggingConfig:
    log_file_path: Optional[str]
    level: Union[str, int]
    console: bool


_CONFIGURED: Optional[LoggingConfig] = None


def _coerce_level(level: Union[str, int, None]) -> int:
    if level is None:
        return logging.INFO
    if isinstance(level, int):
        return level
    # string
    resolved = logging.getLevelName(level.upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def configure_logging(
    log_file_path: Optional[str],
    level: Union[str, int] = "INFO",
    *,
    console: bool = True,
) -> None:
    """
    Идемпотентно настраивает root-логгер.

    - Файл: UTF-8, append.
    - Консоль: stderr.
    - Если файл/директория недоступны — падаем назад на консоль и не валим приложение.
    """

    global _CONFIGURED

    cfg = LoggingConfig(log_file_path=log_file_path, level=level, console=console)
    root = logging.getLogger()
    root.setLevel(_coerce_level(level))

    # Уже настраивали теми же параметрами — только обновили уровень выше.
    if _CONFIGURED == cfg:
        return

    # Снимаем предыдущие handler'ы, чтобы не плодить дубли.
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    attached_any = False

    if log_file_path:
        try:
            from pathlib import Path

            p = Path(log_file_path)
            p.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(p, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
            attached_any = True
        except Exception as e:  # pragma: no cover
            # Не валим приложение из-за невозможности писать в файл
            print(
                f"WARNING: невозможно открыть файл лога '{log_file_path}': {e}",
                file=sys.stderr,
                flush=True,
            )

    if console or not attached_any:
        stream_handler = logging.StreamHandler(stream=sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)
        attached_any = True

    _CONFIGURED = cfg


def get_effective_log_level(default: str = "INFO") -> str:
    """
    Возвращает строковый уровень логирования с учетом env override.

    Env override: DUBLER_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
    """
    env_level = os.environ.get("DUBLER_LOG_LEVEL")
    return env_level.strip() if env_level else default

