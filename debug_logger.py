"""
Централизованный отладочный логгер для записи отладочной информации в файл.
"""

from __future__ import annotations

import logging
import json
import time
from typing import Optional, Dict


class DebugLogger:
    """Класс для централизованного отладочного логирования"""
    
    def __init__(self, log_file_path: str):
        """
        Инициализирует DebugLogger
        
        :param log_file_path: Путь к файлу лога (сохраняется для обратной совместимости)
        """
        self.log_file_path = log_file_path
        self._logger = logging.getLogger("Dubler.DebugLogger")
    
    def log(
        self,
        location: str,
        message: str,
        data: Optional[Dict] = None,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        hypothesis_id: Optional[str] = None
    ) -> None:
        """
        Записывает отладочное сообщение в стандартный `logging`.
        Формат совместим с прежним JSON-lines, но запись в файл выполняет logging handler.
        
        :param location: Местоположение в коде (например, "app.py:8")
        :param message: Текст сообщения
        :param data: Дополнительные данные для логирования (словарь)
        :param session_id: ID сессии (опционально)
        :param run_id: ID запуска (опционально)
        :param hypothesis_id: ID гипотезы (опционально)
        """
        payload = {
            "sessionId": session_id if session_id is not None else "debug-session",
            "runId": run_id if run_id is not None else "run1",
            "hypothesisId": hypothesis_id if hypothesis_id is not None else "A",
            "location": location,
            "message": message,
            "data": data if data is not None else {},
            "timestamp": int(time.time() * 1000),
        }

        try:
            line = json.dumps(payload, ensure_ascii=False)
        except TypeError:
            payload["data"] = repr(data) if data is not None else {}
            line = json.dumps(payload, ensure_ascii=False)

        # По умолчанию считаем такие события DEBUG-диагностикой.
        self._logger.debug("%s", line)


class NoOpDebugLogger:
    """Заглушка IDebugLogger для релизной сборки: вызовы log() игнорируются."""

    def log(
        self,
        location: str,
        message: str,
        data: Optional[Dict] = None,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        hypothesis_id: Optional[str] = None,
    ) -> None:
        pass

