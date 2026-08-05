"""
Токены управления выполнением фоновых операций.

Цель:
- единая, предсказуемая отмена (cancel) и пауза (pause),
- корректная работа cancel даже когда поток стоит на паузе.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class CancelToken:
    _event: threading.Event

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self, message: str = "Операция отменена пользователем") -> None:
        if self._event.is_set():
            # Локальный импорт, чтобы избежать циклов.
            from .exceptions import BackupCancelledError

            raise BackupCancelledError(message)


@dataclass(frozen=True, slots=True)
class PauseToken:
    """
    pause_event семантика:
    - set()   => НЕ на паузе (выполняем)
    - clear() => на паузе (ждём)
    """

    _event: threading.Event

    def is_paused(self) -> bool:
        return not self._event.is_set()

    def pause(self) -> None:
        self._event.clear()

    def resume(self) -> None:
        self._event.set()

    def wait_if_paused(
        self,
        cancel_token: Optional[CancelToken],
        *,
        poll_interval_sec: float = 0.2,
    ) -> None:
        """
        Ждёт снятия паузы небольшими шагами, параллельно проверяя отмену.
        Это гарантирует, что cancel сработает даже когда поток стоит на паузе.
        """
        while not self._event.is_set():
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            # Ждём чуть-чуть, чтобы быстро реагировать на cancel/resume.
            self._event.wait(timeout=poll_interval_sec)
            if poll_interval_sec > 0:
                # Доп. yield для старых систем/интерпретаторов.
                time.sleep(0)

