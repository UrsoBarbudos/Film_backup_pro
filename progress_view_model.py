"""
ViewModel для управления состоянием прогресса копирования
Отвечает за хранение и управление состоянием, отделяя логику от UI
"""

import time
import re
from PySide6.QtCore import QObject, Signal
from speed_calculator import SpeedCalculator


class ProgressViewModel(QObject):
    """ViewModel для управления состоянием прогресса копирования"""
    
    # Сигналы для уведомления об изменении состояния
    # Используем float для copied_mb и total_mb вместо int для байтов, чтобы избежать переполнения int32
    progress_changed = Signal(float, float, float, float, str)  # percent, copied_mb, total_mb, speed_mbps, current_file
    status_changed = Signal(str)  # message
    paused_changed = Signal(bool)  # paused
    cancelled_changed = Signal(bool)  # cancelled
    verification_started = Signal()
    verification_stopped = Signal()
    
    def __init__(self):
        """Инициализация ViewModel"""
        super().__init__()
        
        # Состояние паузы и отмены
        self._is_paused = False
        self._is_cancelled = False
        
        # Статистика прогресса
        self._percent = 0
        self._copied_bytes = 0
        self._total_bytes = 0
        self._speed_mbps = 0.0
        self._current_file = ""
        
        # Статус процесса
        self._status_message = ""
        self._status_type = "copying"  # "scanning", "copying", "verification"
        
        # Состояние проверки
        self._is_verifying = False
        self._verification_start_time = None
        self._verification_total_start_time = None  # Время начала всей проверки (всех файлов)
        self._verification_current_file_index = 0  # Текущий файл (1-based)
        self._verification_total_files = 0  # Всего файлов для проверки
        
        # Калькулятор скорости с EMA для сглаживания
        self._speed_calculator = SpeedCalculator(alpha=0.2)  # Коэффициент 0.2 обеспечивает баланс между стабильностью и реактивностью
    
    @property
    def is_paused(self) -> bool:
        """Возвращает состояние паузы"""
        return self._is_paused
    
    @property
    def is_cancelled(self) -> bool:
        """Возвращает состояние отмены"""
        return self._is_cancelled
    
    @property
    def percent(self) -> int:
        """Возвращает процент выполнения"""
        return self._percent
    
    @property
    def copied_bytes(self) -> int:
        """Возвращает количество скопированных байт"""
        return self._copied_bytes
    
    @property
    def total_bytes(self) -> int:
        """Возвращает общее количество байт"""
        return self._total_bytes
    
    @property
    def speed_mbps(self) -> float:
        """Возвращает скорость в МБ/с"""
        return self._speed_mbps
    
    @property
    def current_file(self) -> str:
        """Возвращает путь к текущему файлу"""
        return self._current_file
    
    @property
    def status_message(self) -> str:
        """Возвращает текущее сообщение статуса"""
        return self._status_message
    
    @property
    def status_type(self) -> str:
        """Возвращает тип статуса: 'scanning', 'copying', 'verification'"""
        return self._status_type
    
    @property
    def is_verifying(self) -> bool:
        """Возвращает состояние проверки"""
        return self._is_verifying
    
    @property
    def verification_start_time(self) -> float:
        """Возвращает время начала проверки (timestamp)"""
        return self._verification_start_time
    
    @property
    def verification_total_start_time(self) -> float:
        """Возвращает время начала всей проверки (timestamp)"""
        return self._verification_total_start_time
    
    @property
    def verification_current_file_index(self) -> int:
        """Возвращает индекс текущего проверяемого файла (1-based)"""
        return self._verification_current_file_index
    
    @property
    def verification_total_files(self) -> int:
        """Возвращает общее количество файлов для проверки"""
        return self._verification_total_files
    
    def set_paused(self, paused: bool):
        """
        Устанавливает состояние паузы
        
        :param paused: True если на паузе, False если работает
        """
        if self._is_paused != paused:
            self._is_paused = paused
            self.paused_changed.emit(paused)
    
    def set_cancelled(self, cancelled: bool):
        """
        Устанавливает состояние отмены
        
        :param cancelled: True если отменено, False если работает
        """
        if self._is_cancelled != cancelled:
            self._is_cancelled = cancelled
            self.cancelled_changed.emit(cancelled)
    
    def update_progress(self, percent: float, copied_bytes: int, total_bytes: int, speed_mbps: float, current_file: str):
        """
        Обновляет прогресс копирования
        
        Использует EMA для сглаживания скорости, что обеспечивает более стабильные
        и точные прогнозы оставшегося времени.
        
        :param percent: Процент выполнения (0-100)
        :param copied_bytes: Скопировано байт
        :param total_bytes: Всего байт
        :param speed_mbps: Текущая скорость в МБ/с (будет сглажена через EMA)
        :param current_file: Путь к текущему файлу
        """
        self._percent = percent
        self._copied_bytes = copied_bytes
        self._total_bytes = total_bytes
        self._current_file = current_file
        
        # Сглаживаем скорость с помощью EMA
        smoothed_speed = self._speed_calculator.update(speed_mbps)
        self._speed_mbps = smoothed_speed
        
        # Конвертируем байты в МБ для передачи через сигнал, чтобы избежать переполнения int32
        copied_mb = float(copied_bytes) / (1024.0 * 1024.0)
        total_mb = float(total_bytes) / (1024.0 * 1024.0)
        # Используем сглаженную скорость для более стабильных прогнозов ETA
        self.progress_changed.emit(percent, copied_mb, total_mb, smoothed_speed, current_file)
    
    def update_status(self, message: str):
        """
        Обновляет статусное сообщение и определяет тип статуса
        
        :param message: Текстовое сообщение статуса
        """
        self._status_message = message
        message_lower = message.lower()
        
        # Определяем тип статуса
        if "сканирование" in message_lower or "scanning" in message_lower:
            new_status_type = "scanning"
        elif "проверка" in message_lower or "verification" in message_lower:
            new_status_type = "verification"
            # Парсим информацию о прогрессе проверки из сообщения
            # Формат: "Проверка файла {verify_index} из {total_files}: {filename}"
            match = re.search(r'Проверка файла (\d+) из (\d+):', message)
            if match:
                self._verification_current_file_index = int(match.group(1))
                self._verification_total_files = int(match.group(2))
        elif "копирование" in message_lower or "copying" in message_lower:
            new_status_type = "copying"
        else:
            new_status_type = self._status_type  # Сохраняем текущий тип
        
        # Если тип изменился, обновляем состояние проверки
        if new_status_type != self._status_type:
            if new_status_type == "verification":
                self.start_verification()
            elif self._status_type == "verification":
                self.stop_verification()
        
        self._status_type = new_status_type
        self.status_changed.emit(message)
    
    def start_verification(self):
        """Начинает проверку файла"""
        if not self._is_verifying:
            self._is_verifying = True
            self._verification_start_time = time.time()
            # Сохраняем время начала всей проверки (если еще не сохранено)
            if self._verification_total_start_time is None:
                self._verification_total_start_time = time.time()
            self.verification_started.emit()
    
    def stop_verification(self):
        """Останавливает проверку файла"""
        if self._is_verifying:
            self._is_verifying = False
            self._verification_start_time = None
            self._verification_total_start_time = None
            self._verification_current_file_index = 0
            self._verification_total_files = 0
            self.verification_stopped.emit()
    
    def reset(self):
        """Сбрасывает состояние ViewModel к начальному"""
        self._is_paused = False
        self._is_cancelled = False
        self._percent = 0
        self._copied_bytes = 0
        self._total_bytes = 0
        self._speed_mbps = 0.0
        self._current_file = ""
        self._status_message = ""
        self._status_type = "copying"
        self._is_verifying = False
        self._verification_start_time = None
        self._verification_total_start_time = None
        self._verification_current_file_index = 0
        self._verification_total_files = 0
        # Сбрасываем калькулятор скорости
        self._speed_calculator.reset()
