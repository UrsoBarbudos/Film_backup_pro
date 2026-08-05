"""
Модуль для обработки повторных попыток при временных ошибках.
"""

import time
import logging
from typing import Callable, Any, Optional, TypeVar

from .exceptions import is_temporary_error

T = TypeVar('T')

logger = logging.getLogger(__name__)


class RetryHandler:
    """
    Класс для обработки повторных попыток при временных ошибках.
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        delay: float = 1.0,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Инициализация обработчика повторных попыток
        
        :param max_attempts: Максимальное количество попыток (по умолчанию 3)
        :param delay: Задержка между попытками в секундах (по умолчанию 1.0)
        :param log_callback: Функция для логирования операций (опционально)
        """
        self.max_attempts = max_attempts
        self.delay = delay
        self.log_callback = log_callback or (lambda msg: None)
    
    def retry_on_temporary_error(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """
        Выполняет функцию с повторными попытками при временных ошибках.
        
        Если функция выбрасывает временную ошибку, выполняется повторная попытка
        после задержки. После исчерпания попыток исключение пробрасывается дальше.
        
        :param func: Функция для выполнения
        :param args: Позиционные аргументы для функции
        :param kwargs: Именованные аргументы для функции
        :return: Результат выполнения функции
        :raises: Исключение, если все попытки исчерпаны или ошибка не временная
        """
        last_error = None
        
        for attempt in range(1, self.max_attempts + 1):
            logger.debug(
                "Retry attempt %d/%d for %s",
                attempt,
                self.max_attempts,
                func.__name__ if hasattr(func, "__name__") else str(func),
            )
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                last_error = e
                logger.debug(
                    "Exception in retry attempt %d/%d: %s (%s), temporary=%s",
                    attempt,
                    self.max_attempts,
                    str(e),
                    type(e).__name__,
                    is_temporary_error(e),
                )
                
                # Если ошибка не временная, пробрасываем сразу
                if not is_temporary_error(e):
                    self.log_callback(
                        f"⚠️  Ошибка не является временной, повторная попытка не выполняется: {type(e).__name__}: {e}"
                    )
                    raise
                
                # Если это последняя попытка, пробрасываем исключение
                if attempt == self.max_attempts:
                    self.log_callback(
                        f"❌ Исчерпаны попытки ({self.max_attempts}) для операции. "
                        f"Последняя ошибка: {type(e).__name__}: {e}"
                    )
                    raise
                
                # Логируем попытку и ждем перед следующей
                self.log_callback(
                    f"🔄 Временная ошибка при выполнении операции (попытка {attempt}/{self.max_attempts}): "
                    f"{type(e).__name__}: {e}. Повтор через {self.delay}с..."
                )
                time.sleep(self.delay)
        
        # Этот код не должен выполняться, но на всякий случай
        if last_error:
            raise last_error
        raise RuntimeError("Неожиданная ошибка в RetryHandler")
