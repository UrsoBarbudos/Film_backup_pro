from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from interfaces import (
    IConfig,
    IFileCopier,
    IFileSystemInterface,
    IFileVerifier,
    ITelegramClient,
)

from .backup_logger import BackupLogger
from .backup_notifier import BackupNotifier
from .control_tokens import CancelToken, PauseToken
from .hash_storage import HashStorage
from .retry_handler import RetryHandler
from sleep_prevention import SleepPrevention


@dataclass(frozen=True, slots=True)
class BackupRunConfig:
    destination_root: str
    source_drives: list[str]
    verification_mode: str
    create_md_log: bool
    prevent_sleep: bool


@dataclass(frozen=True, slots=True)
class BackupTokens:
    pause_event: threading.Event
    pause_token: PauseToken
    cancel_token: CancelToken

    @classmethod
    def from_legacy(
        cls,
        pause_event: Optional[threading.Event] = None,
        pause_token: Optional[PauseToken] = None,
        cancel_token: Optional[CancelToken] = None,
    ) -> "BackupTokens":
        """
        Собирает токены из legacy-набора параметров:
        - если event'ы не переданы, создаём новые (pause_event по умолчанию 'set' — не на паузе)
        - если token'ы не переданы, создаём их на основе event'ов
        """
        if pause_event is None:
            pause_event = threading.Event()
            pause_event.set()  # по умолчанию не на паузе

        if pause_token is None:
            pause_token = PauseToken(pause_event)
        if cancel_token is None:
            cancel_token = CancelToken(threading.Event())

        return cls(
            pause_event=pause_event,
            pause_token=pause_token,
            cancel_token=cancel_token,
        )


@dataclass(frozen=True, slots=True)
class BackupCallbacks:
    log_callback: Callable[[str], None]
    progress_callback: Optional[Callable[..., Any]]
    signals: Optional[Any]
    verification_action_callback: Optional[Callable[[str, str, str], str]]
    copy_conflict_action_callback: Optional[Callable[[str, str, str], Tuple[str, bool]]]
    success_callback: Optional[Callable[[], Any]]
    progress_batcher: Optional[Any]


@dataclass(frozen=True, slots=True)
class BackupDeps:
    file_system: IFileSystemInterface
    config: Optional[IConfig] = None
    file_copier: Optional[IFileCopier] = None
    file_verifier: Optional[IFileVerifier] = None
    hash_storage: Optional[HashStorage] = None
    retry_handler: Optional[RetryHandler] = None
    backup_logger: Optional[BackupLogger] = None
    backup_notifier: Optional[BackupNotifier] = None
    telegram_client: Optional[ITelegramClient] = None
    source_backup_marker_service: Optional[Any] = None
    sleep_prevention_factory: Callable[[], Any] = SleepPrevention
