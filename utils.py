"""
Вспомогательные функции для Dублёр
"""

import re
from typing import Optional, Dict, Tuple, List, Callable, Any
from datetime import datetime
from interfaces import IFileSystemInterface
import logging


logger = logging.getLogger(__name__)

def resolve_file_system(file_system: Optional[IFileSystemInterface]) -> IFileSystemInterface:
    """
    Резолвит IFileSystemInterface.

    Фаза 4 (финализация DI): `file_system` должен передаваться явно.
    Любой вызов с `None` — ошибка (hidden dependency).
    """
    if file_system is None:
        raise ValueError(
            "file_system must be provided (explicit DI). "
            "Pass it from composition root and do not rely on implicit fallbacks."
        )
    return file_system

def _listdir_shallow(
    directory: str,
    file_system: IFileSystemInterface,
) -> Tuple[List[str], List[str]]:
    """
    Возвращает (dirnames, filenames) ТОЛЬКО для текущей директории.

    Важно: делаем через первый yield `fs.walk()`, чтобы не использовать `os.scandir/glob`
    вне инфраструктурного слоя.
    """
    try:
        _dirpath, dirnames, filenames = next(file_system.walk(directory), (directory, [], []))
        return (list(dirnames), list(filenames))
    except Exception:
        return ([], [])

def get_directory_size(
    path: str,
    file_system: Optional[IFileSystemInterface] = None,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> int:
    """
    Вычисляет общий размер директории в байтах.
    
    :param path: Путь к директории
    :param file_system: Интерфейс файловой системы (опционально, для обратной совместимости)
    :return: Размер в байтах
    """
    
    
    file_system = resolve_file_system(file_system)
    
    fs = file_system
    total_size = 0
    try:
        for dirpath, dirnames, filenames in fs.walk(path):
            if should_cancel and should_cancel():
                return 0

            for filename in filenames:
                if should_cancel and should_cancel():
                    return 0

                filepath = fs.join(dirpath, filename)
                try:
                    total_size += fs.getsize(filepath)
                except (OSError, FileNotFoundError):
                    # Игнорируем файлы, к которым нет доступа
                    pass
    except (OSError, PermissionError):
        # Если нет доступа к директории, возвращаем 0
        
        return 0
    
    
    return total_size

def get_path_size(
    path: str,
    file_system: Optional[IFileSystemInterface] = None,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> int:
    """
    Вычисляет размер файла или папки в байтах.
    Универсальная функция для работы с любыми путями.
    
    :param path: Путь к файлу или папке
    :param file_system: Интерфейс файловой системы (опционально, для обратной совместимости)
    :return: Размер в байтах (0 если путь не существует или недоступен)
    """
    
    
    file_system = resolve_file_system(file_system)
    
    fs = file_system
    if not fs.exists(path):
        
        return 0
    
    try:
        if fs.isfile(path):
            if should_cancel and should_cancel():
                return 0
            size = fs.getsize(path)
            
            return size
        elif fs.isdir(path):
            size = get_directory_size(path, file_system=fs, should_cancel=should_cancel)
            
            return size
    except (OSError, PermissionError):
        # Игнорируем ошибки доступа
        
        return 0
    
    
    return 0

def validate_path(path: str, *, file_system: IFileSystemInterface) -> bool:
    """
    Валидирует путь источника.
    Утилитная функция для валидации путей без необходимости создания SourceManager.
    
    :param path: Путь для проверки
    :param file_system: Интерфейс файловой системы (обязателен, explicit DI)
    :return: True если путь валиден, False в противном случае
    """
    return file_system.exists(path)

def get_disk_free_space(
    path: str,
    *,
    file_system: IFileSystemInterface,
) -> Tuple[int, int, int]:
    """
    Получает информацию о свободном месте на диске для указанного пути.
    
    :param path: Путь к файлу или папке на диске
    :param file_system: Интерфейс файловой системы (обязателен, explicit DI)
    :return: Кортеж (total, used, free) в байтах. Если путь недоступен, возвращает (0, 0, 0)
    """
    try:
        if not validate_path(path, file_system=file_system):
            # Если путь не существует, используем родительскую директорию
            parent_path = file_system.dirname(path) if file_system.dirname(path) else path
            if not validate_path(parent_path, file_system=file_system):
                return (0, 0, 0)
            path = parent_path
        
        # Если путь - файл, используем его директорию
        if file_system.isfile(path):
            path = file_system.dirname(path) or path
        
        # Получаем информацию о диске
        return file_system.disk_usage(path)
    except (OSError, PermissionError) as e:
        logger.warning("Не удалось получить информацию о диске для %s: %s", path, e)
        return (0, 0, 0)

def format_size(size_bytes: int) -> str:
    """
    Форматирует размер в байтах в читаемый формат (GB, MB, KB).
    Использует десятичные единицы (1000^3) для соответствия стандарту SI и macOS Finder.
    
    :param size_bytes: Размер в байтах
    :return: Отформатированная строка (например, "24 GB", "1.3 MB")
    """
    
    
    # Защита от отрицательных значений
    if size_bytes < 0:
        logger.warning("format_size получил отрицательное значение: %s", size_bytes)
        return "0 B"
    
    if size_bytes == 0:
        return "0 B"
    
    # Используем десятичные единицы (1000^3) для соответствия macOS Finder
    gb = size_bytes / (1000 ** 3)
    mb = size_bytes / (1000 ** 2)
    kb = size_bytes / 1000
    
    if gb >= 1:
        return f"{gb:.2f} GB".replace(".00", "")
    elif mb >= 1:
        return f"{mb:.2f} MB".replace(".00", "")
    elif kb >= 1:
        return f"{kb:.2f} KB".replace(".00", "")
    else:
        return f"{size_bytes} B"

def get_size_icon(size_bytes: int) -> str:
    """
    Возвращает иконку (эмодзи) в зависимости от размера папки.
    
    :param size_bytes: Размер в байтах
    :return: Эмодзи иконка
    """
    gb = size_bytes / (1024 ** 3)
    
    if gb >= 10:
        return "📹"  # Видеокассета для больших папок
    elif gb >= 1:
        return "🎵"  # Нота для средних папок
    else:
        return "📄"  # Документ для маленьких папок

def get_file_sizes_for_compare(
    path_a: str,
    path_b: str,
    file_system: IFileSystemInterface,
    retry_handler: Optional[Any] = None,
) -> Tuple[int, int]:
    """
    Возвращает размеры двух файлов для последующего сравнения.
    При отсутствии файла или ошибке при получении размера выбрасывает исключение.

    :param path_a: Путь к первому файлу
    :param path_b: Путь ко второму файлу
    :param file_system: Интерфейс файловой системы
    :param retry_handler: Опционально — обработчик повторов (метод retry_on_temporary_error)
    :return: Кортеж (size_a, size_b) в байтах
    :raises ValueError: Если один из файлов не найден
    :raises OSError: При ошибке при получении размера
    """
    if not file_system.exists(path_a):
        raise ValueError(f"Исходный файл не найден: {path_a}")
    if not file_system.exists(path_b):
        raise ValueError(f"Целевой файл не найден: {path_b}")

    get_size = file_system.getsize
    if retry_handler is not None:
        size_a = retry_handler.retry_on_temporary_error(get_size, path_a)
        size_b = retry_handler.retry_on_temporary_error(get_size, path_b)
    else:
        size_a = get_size(path_a)
        size_b = get_size(path_b)
    return (size_a, size_b)


def validate_file_size(
    source_path: str,
    destination_path: str,
    file_system: IFileSystemInterface
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, совпадают ли размеры исходного и целевого файлов.

    :param source_path: Путь к исходному файлу
    :param destination_path: Путь к целевому файлу
    :param file_system: Интерфейс файловой системы для работы с файлами
    :return: Кортеж (валиден ли файл: bool, сообщение об ошибке: Optional[str])
             Возвращает (True, None) если размеры совпадают
             Возвращает (False, error_message) если размеры не совпадают или произошла ошибка
    """
    try:
        source_size, destination_size = get_file_sizes_for_compare(
            source_path, destination_path, file_system, retry_handler=None
        )
        if source_size == destination_size:
            return (True, None)
        error_msg = f"Размеры не совпадают (исходный: {format_size(source_size)}, целевой: {format_size(destination_size)})"
        return (False, error_msg)
    except ValueError as e:
        return (False, str(e))
    except OSError as e:
        return (False, f"Ошибка при проверке размеров файлов: {e}")
    except Exception as e:
        return (False, f"Неожиданная ошибка при проверке размеров: {e}")


def safe_add_bytes(a: int, b: int) -> int:
    """
    Безопасное сложение байтов с защитой от переполнения.
    
    :param a: Первое значение в байтах
    :param b: Второе значение в байтах
    :return: Сумма с защитой от переполнения (максимум sys.maxsize)
    """
    import sys
    try:
        result = a + b
        # Проверяем переполнение: если результат стал отрицательным или меньше одного из слагаемых
        if result < 0 or (a > 0 and b > 0 and result < a):
            return sys.maxsize  # Возвращаем максимальное значение int
        return result
    except OverflowError:
        return sys.maxsize
