"""
Composition root (единая точка сборки зависимостей).

Идея:
- Создание и связывание зависимостей делаем здесь (явно).
- В остальном коде зависимости должны передаваться через конструкторы/параметры.

Важно: чтобы не ловить циклические импорты, тяжелые импорты делаем внутри builder-функций.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from interfaces import IConfig, IFileSystemInterface, IDebugLogger, ITelegramClient


@dataclass(frozen=True, slots=True)
class AppContext:
    """Набор общих зависимостей приложения (shared инфраструктура)."""

    config: IConfig
    file_system: IFileSystemInterface
    debug_logger: IDebugLogger
    telegram_client: ITelegramClient
    source_backup_marker_service: object


_CURRENT_CONTEXT: Optional[AppContext] = None


def set_current_context(context: Optional[AppContext]) -> None:
    """Устанавливает текущий контекст (для legacy-адаптеров/переходного периода)."""

    global _CURRENT_CONTEXT
    _CURRENT_CONTEXT = context


def get_current_context() -> Optional[AppContext]:
    """Возвращает текущий контекст, если он установлен."""

    return _CURRENT_CONTEXT


def require_current_context() -> AppContext:
    """Возвращает текущий контекст или выбрасывает ошибку (для строгих мест)."""

    context = _CURRENT_CONTEXT
    if context is None:
        raise RuntimeError(
            "AppContext не установлен. Ожидается сборка зависимостей через composition.build_app_context()."
        )
    return context


def build_app_context(*, settings_file: Optional[str] = None, log_file_path: Optional[str] = None) -> AppContext:
    """
    Prod-сборка контекста.

    :param settings_file: путь к settings.json (опционально)
    :param log_file_path: путь к debug-логу (опционально)
    """

    from config import Config
    from debug_logger import DebugLogger, NoOpDebugLogger
    from repositories import FileSystemRepository
    from paths import get_debug_log_path
    from integrations import TelegramClient
    from source_backup_marker import SourceBackupMarkerService

    config = Config(settings_file=settings_file)
    file_system = FileSystemRepository()
    agent_log_raw = os.environ.get("DUBLER_AGENT_LOG", "1").strip().lower()
    if agent_log_raw in ("0", "false", "no"):
        debug_logger = NoOpDebugLogger()
    else:
        debug_logger = DebugLogger(log_file_path=log_file_path or get_debug_log_path())

    context = AppContext(
        config=config,
        file_system=file_system,
        debug_logger=debug_logger,
        telegram_client=TelegramClient(),
        source_backup_marker_service=SourceBackupMarkerService(),
    )
    set_current_context(context)
    return context


def build_test_context(
    *,
    config: Optional[IConfig] = None,
    file_system: Optional[IFileSystemInterface] = None,
    debug_logger: Optional[IDebugLogger] = None,
    telegram_client: Optional[ITelegramClient] = None,
    source_backup_marker_service: Optional[object] = None,
    settings_file: Optional[str] = None,
    log_file_path: Optional[str] = None,
) -> AppContext:
    """
    Test/dev-сборка контекста с возможностью подмены зависимостей.
    Если зависимости не переданы — используются стандартные реализации.
    """

    if config is None:
        from config import Config

        config = Config(settings_file=settings_file)
    if file_system is None:
        from repositories import FileSystemRepository

        file_system = FileSystemRepository()
    if debug_logger is None:
        from debug_logger import DebugLogger, NoOpDebugLogger
        from paths import get_debug_log_path

        agent_log_raw = os.environ.get("DUBLER_AGENT_LOG", "1").strip().lower()
        if agent_log_raw in ("0", "false", "no"):
            debug_logger = NoOpDebugLogger()
        else:
            debug_logger = DebugLogger(log_file_path=log_file_path or get_debug_log_path())
    if telegram_client is None:
        from integrations import TelegramClient

        telegram_client = TelegramClient()
    if source_backup_marker_service is None:
        from source_backup_marker import SourceBackupMarkerService

        source_backup_marker_service = SourceBackupMarkerService()

    context = AppContext(
        config=config,
        file_system=file_system,
        debug_logger=debug_logger,
        telegram_client=telegram_client,
        source_backup_marker_service=source_backup_marker_service,
    )
    set_current_context(context)
    return context
