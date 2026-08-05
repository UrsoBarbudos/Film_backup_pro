"""
Модуль с исключениями для процесса резервного копирования.
"""

import errno


class BackupCancelledError(Exception):
    """Исключение для отмены процесса резервного копирования"""
    pass


def is_temporary_error(error: Exception) -> bool:
    """
    Определяет, является ли ошибка временной и требующей повторной попытки.
    
    Временными считаются:
    - PermissionError - временные проблемы с правами доступа
    - OSError с кодами EAGAIN, EINTR, EBUSY - временные системные ошибки
    
    :param error: Исключение для проверки
    :return: True если ошибка временная, False в противном случае
    """
    if isinstance(error, PermissionError):
        return True
    
    if isinstance(error, OSError):
        # EAGAIN - ресурс временно недоступен
        # EINTR - операция прервана сигналом
        # EBUSY - ресурс занят
        if error.errno in (errno.EAGAIN, errno.EINTR, errno.EBUSY):
            return True
    
    return False
