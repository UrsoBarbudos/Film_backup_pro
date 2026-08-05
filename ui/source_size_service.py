"""
Сервис фонового расчёта размеров источников (файлы/папки).

Требования:
- не содержит ссылок на UI-компоненты;
- даёт сигнал с результатом;
- поддерживает мягкую отмену без QThread.terminate().
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QThread, Signal

from source_manager import SourceManager
from interfaces import IDebugLogger


class _SizeCalculationWorker(QThread):
    """
    Worker поток для вычисления размера источника в фоне.

    Важно: размер эмитится как строка, чтобы не упираться в ограничения Qt по int.
    """

    size_ready = Signal(str, str)  # source_path, size_bytes_str

    def __init__(
        self,
        *,
        source_path: str,
        source_manager: SourceManager,
        should_cancel: Callable[[], bool],
        debug_logger: Optional[IDebugLogger] = None,
    ) -> None:
        super().__init__()
        self._source_path = source_path
        self._source_manager = source_manager
        self._should_cancel = should_cancel
        self._debug_logger = debug_logger

    def run(self) -> None:
        if self._debug_logger:
            self._debug_logger.log(
                location="ui/source_size_service.py:_SizeCalculationWorker.run",
                message="Size worker START",
                data={"source_path": self._source_path},
            )

        if self._should_cancel() or self.isInterruptionRequested():
            return

        size_bytes = self._source_manager.get_source_size(
            self._source_path,
            use_cache=False,
            should_cancel=self._should_cancel,
        )

        # Если отменили во время вычисления — не эмитим результат.
        if self._should_cancel() or self.isInterruptionRequested():
            return

        if self._debug_logger:
            self._debug_logger.log(
                location="ui/source_size_service.py:_SizeCalculationWorker.run",
                message="Size worker END - emitting size_ready",
                data={"source_path": self._source_path, "size_bytes": size_bytes},
            )

        self.size_ready.emit(self._source_path, str(size_bytes))


@dataclass(slots=True)
class _Task:
    worker: _SizeCalculationWorker
    cancel_event: threading.Event


class SourceSizeService(QObject):
    """
    Оркестратор фоновых задач вычисления размеров.

    Не знает о UI. Общение наружу — через сигнал size_ready.
    """

    size_ready = Signal(str, str)  # source_path, size_bytes_str

    def __init__(
        self,
        *,
        source_manager: SourceManager,
        debug_logger: Optional[IDebugLogger] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._source_manager = source_manager
        self._debug_logger = debug_logger
        self._tasks: Dict[str, _Task] = {}

    def start(self, source_path: str) -> None:
        """
        Запускает вычисление размера источника, если задача ещё не запущена.
        """
        if source_path in self._tasks:
            return

        cancel_event = threading.Event()

        def should_cancel() -> bool:
            return cancel_event.is_set()

        worker = _SizeCalculationWorker(
            source_path=source_path,
            source_manager=self._source_manager,
            should_cancel=should_cancel,
            debug_logger=self._debug_logger,
        )
        worker.size_ready.connect(self._on_worker_ready)
        worker.finished.connect(lambda: self._on_worker_finished(source_path))

        self._tasks[source_path] = _Task(worker=worker, cancel_event=cancel_event)
        worker.start()

    def cancel(self, source_path: str) -> None:
        """
        Мягко отменяет задачу (кооперативно).
        """
        task = self._tasks.get(source_path)
        if not task:
            return
        task.cancel_event.set()
        task.worker.requestInterruption()
        # Небольшой wait, чтобы быстрее освобождать ресурсы и не копить висящие worker'ы.
        # Важно: таймаут малый, чтобы не фризить UI.
        task.worker.wait(200)

    def cancel_all(self) -> None:
        """
        Мягко отменяет все задачи.
        """
        for task in list(self._tasks.values()):
            task.cancel_event.set()
            task.worker.requestInterruption()
            task.worker.wait(200)

    def _on_worker_ready(self, source_path: str, size_bytes_str: str) -> None:
        # Пробрасываем наружу.
        self.size_ready.emit(source_path, size_bytes_str)

    def _on_worker_finished(self, source_path: str) -> None:
        # Освобождаем worker после завершения.
        task = self._tasks.pop(source_path, None)
        if task:
            task.worker.deleteLater()

