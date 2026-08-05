"""
Модуль для выбора стратегии копирования файлов в зависимости от их размера.
"""

from enum import Enum


LARGE_FILE_THRESHOLD_BYTES = 100 * 1024 * 1024  # 100 МБ


class CopyMethod(Enum):
    """Методы копирования файлов"""
    SHUTIL = "shutil"
    BLOCK = "block"


def get_copy_method(file_size: int) -> CopyMethod:
    """
    Выбирает метод копирования по размеру файла.

    :param file_size: Размер файла в байтах
    :return: Метод копирования (CopyMethod)
    """
    if file_size < LARGE_FILE_THRESHOLD_BYTES:
        return CopyMethod.SHUTIL
    return CopyMethod.BLOCK
