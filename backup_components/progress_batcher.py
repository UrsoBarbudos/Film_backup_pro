"""
Модуль для батчинга обновлений прогресса копирования.
Использует QTimer для группировки частых обновлений и предотвращения блокировки UI потока.
"""

import threading
import logging
from PySide6.QtCore import QObject, Signal, QTimer, QMetaObject, Qt, Slot


logger = logging.getLogger(__name__)


class ProgressUpdateBatcher(QObject):
    """
    Класс для батчинга обновлений прогресса копирования.
    
    Накапливает обновления прогресса из фонового потока и отправляет их
    в UI поток через QTimer с заданным интервалом (по умолчанию 150мс).
    Это предотвращает блокировку UI потока при частых обновлениях.
    """
    
    # Сигнал для отправки обновлений прогресса в UI
    progress_updated = Signal(int, float, float, float, str)  # percent, copied_mb, total_mb, speed_mbps, current_file
    
    def __init__(self, update_interval_ms: int = 150):
        """
        Инициализация батчера обновлений прогресса
        
        :param update_interval_ms: Интервал обновления UI в миллисекундах (100-200мс)
        """
        super().__init__()
        
        # Проверяем корректность интервала
        if update_interval_ms < 100:
            update_interval_ms = 100
        elif update_interval_ms > 200:
            update_interval_ms = 200
        
        self.update_interval_ms = update_interval_ms
        
        # Thread-safe состояние прогресса
        self._lock = threading.Lock()
        self._pending_update = False
        
        # Последние значения прогресса
        self._percent = 0
        self._copied_mb = 0.0
        self._total_mb = 0.0
        self._speed_mbps = 0.0
        self._current_file = ""
        
        # QTimer для периодической отправки обновлений
        self._timer = QTimer()
        self._timer.timeout.connect(self._emit_batched_update)
        self._timer.setSingleShot(False)  # Повторяющийся таймер
        self._timer.setInterval(self.update_interval_ms)
        
        # Флаг для отслеживания активности
        self._is_active = False
    
    def start(self):
        """Запускает таймер для периодической отправки обновлений"""
        if not self._is_active:
            self._is_active = True
            self._timer.start()
    
    def stop(self):
        """Останавливает таймер и отправляет финальное обновление"""
        self._is_active = False
        self._timer.stop()
        # Отправляем финальное обновление, если есть накопленные данные
        # Проверяем наличие ожидающего обновления БЕЗ блокировки, чтобы избежать deadlock
        # (так как _emit_batched_update() сам берет блокировку)
        should_emit = False
        with self._lock:
            should_emit = self._pending_update
        if should_emit:
            self._emit_batched_update()
    
    def update_progress(
        self, 
        percent: int, 
        copied_bytes: int, 
        total_bytes: int, 
        speed_mbps: float, 
        current_file: str
    ):
        """
        Обновляет состояние прогресса (вызывается из фонового потока)
        
        :param percent: Процент выполнения (0-100)
        :param copied_bytes: Скопировано байт
        :param total_bytes: Всего байт
        :param speed_mbps: Скорость в МБ/с
        :param current_file: Путь к текущему файлу
        """
        # Конвертируем байты в мегабайты для передачи через сигнал
        copied_mb = float(copied_bytes) / (1024.0 * 1024.0)
        total_mb = float(total_bytes) / (1024.0 * 1024.0)
        
        # Thread-safe обновление состояния
        with self._lock:
            self._percent = percent
            self._copied_mb = copied_mb
            self._total_mb = total_mb
            self._speed_mbps = speed_mbps
            self._current_file = current_file
            self._pending_update = True
        
        # Запускаем таймер, если он еще не запущен
        if not self._is_active:
            self.start()
    
    @Slot()
    def _emit_batched_update(self):
        """
        Отправляет накопленное обновление через сигнал (вызывается из главного потока Qt)
        Этот метод вызывается QTimer и должен выполняться в главном потоке Qt.
        """
        # Получаем последние значения thread-safe способом
        with self._lock:
            if not self._pending_update:
                return
            
            percent = self._percent
            copied_mb = self._copied_mb
            total_mb = self._total_mb
            speed_mbps = self._speed_mbps
            current_file = self._current_file
            
            # Сбрасываем флаг ожидающего обновления
            self._pending_update = False
        
        # Отправляем сигнал в UI поток
        self.progress_updated.emit(percent, copied_mb, total_mb, speed_mbps, current_file)
    
    def force_update(self):
        """
        Принудительно отправляет текущее состояние прогресса немедленно
        (используется для финальных обновлений)
        Вызывается из фонового потока, поэтому использует QMetaObject.invokeMethod
        для безопасного вызова _emit_batched_update() в главном потоке Qt.
        """
        logger.debug("force_update() entry (pending=%s, active=%s)", self._pending_update, self._is_active)
        with self._lock:
            if self._pending_update or self._is_active:
                # Используем QMetaObject.invokeMethod для безопасного вызова из фонового потока
                # Это гарантирует, что _emit_batched_update() будет вызван в главном потоке Qt
                QMetaObject.invokeMethod(
                    self,
                    "_emit_batched_update",
                    Qt.ConnectionType.QueuedConnection
                )
        logger.debug("force_update() exit")