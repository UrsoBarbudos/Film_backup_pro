"""
Централизованные пути приложения (переносимость).

Фаза A (План 3): убрать абсолютные пути из кода и вычислять runtime-пути
по правилам платформы.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Dubler"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_app_data_dir() -> str:
    """
    Возвращает директорию для данных приложения.

    macOS: ~/Library/Application Support/Dubler
    """
    # Для smoke-тестов/CI/песочниц: возможность направить данные приложения в безопасное место.
    # Не влияет на обычный запуск, если переменные окружения не заданы.
    override = os.environ.get("FILM_BACKUP_PRO_APP_DATA_DIR") or os.environ.get("DUBLER_APP_DATA_DIR")
    if override:
        return str(_ensure_dir(Path(override)))

    home = Path.home()
    if sys.platform == "darwin":
        return str(_ensure_dir(home / "Library" / "Application Support" / APP_NAME))

    # Fallback (на будущее): XDG-ish в домашней директории без внешних зависимостей
    return str(_ensure_dir(home / f".{APP_NAME.lower()}" / "data"))


def get_logs_dir() -> str:
    """
    Возвращает директорию для runtime-логов.

    macOS: ~/Library/Logs/Dubler
    """
    home = Path.home()
    if sys.platform == "darwin":
        return str(_ensure_dir(home / "Library" / "Logs" / APP_NAME))

    # Fallback (на будущее)
    base = Path(os.environ.get("XDG_STATE_HOME", str(home / ".local" / "state")))
    return str(_ensure_dir(base / APP_NAME / "logs"))


def get_fallback_reports_dir() -> str:
    """Возвращает локальный каталог для отчётов при отказе диска назначения."""
    return str(_ensure_dir(Path(get_app_data_dir()) / "reports"))


def get_debug_log_path() -> str:
    """Полный путь к runtime debug-логу приложения."""
    return str(Path(get_logs_dir()) / "debug.log")


def get_assets_animations_dir() -> str:
    """
    Путь к директории assets/animations (PNG-кадры для DropZone анимации).

    В режиме разработки — каталог assets/animations в корне проекта.
    В собранном приложении (frozen) — поддиректория в sys._MEIPASS.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "assets", "animations")
    return str(Path(__file__).resolve().parent / "assets" / "animations")
