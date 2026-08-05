"""
Реализация IFileSystemInterface через стандартные библиотеки Python.
Использует os, os.path и shutil для работы с файловой системой.
"""

import os
import shutil
import tempfile
from typing import Iterator, Tuple, List, Any, IO, Callable, Optional


class FileSystemRepository:
    """Реализация интерфейса файловой системы через стандартные библиотеки"""
    
    def exists(self, path: str) -> bool:
        """Проверяет существование пути"""
        return os.path.exists(path)
    
    def isfile(self, path: str) -> bool:
        """Проверяет, является ли путь файлом"""
        return os.path.isfile(path)
    
    def isdir(self, path: str) -> bool:
        """Проверяет, является ли путь директорией"""
        return os.path.isdir(path)
    
    def getsize(self, path: str) -> int:
        """Возвращает размер файла в байтах"""
        return os.path.getsize(path)
    
    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        """Создает директорию (рекурсивно)"""
        os.makedirs(path, exist_ok=exist_ok)
    
    def walk(self, path: str) -> Iterator[Tuple[str, List[str], List[str]]]:
        """
        Обходит директорию рекурсивно на основе os.scandir() для лучшей производительности.
        Возвращает (dirpath, dirnames, filenames)
        """
        yield from self.walk_with_errors(path)

    def walk_with_errors(
        self,
        path: str,
        on_error: Optional[Callable[[str, OSError], None]] = None,
    ) -> Iterator[Tuple[str, List[str], List[str]]]:
        """Обходит дерево и сообщает ошибки доступа вызывающему коду."""
        dirs = []
        files = []
        
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            dirs.append(entry.name)
                        elif entry.is_file(follow_symlinks=False):
                            files.append(entry.name)
                    except OSError as exc:
                        if on_error:
                            on_error(entry.path, exc)
                        continue
        except OSError as exc:
            if on_error:
                on_error(path, exc)
        
        yield (path, dirs, files)
        
        # Рекурсивно обрабатываем поддиректории
        for dirname in dirs:
            dirpath = os.path.join(path, dirname)
            yield from self.walk_with_errors(dirpath, on_error)
    
    def join(self, *paths: str) -> str:
        """Объединяет пути"""
        return os.path.join(*paths)
    
    def basename(self, path: str) -> str:
        """Возвращает базовое имя пути"""
        return os.path.basename(path)
    
    def dirname(self, path: str) -> str:
        """Возвращает директорию пути"""
        return os.path.dirname(path)
    
    def relpath(self, path: str, start: str) -> str:
        """Возвращает относительный путь от start до path"""
        return os.path.relpath(path, start)
    
    def open(self, path: str, mode: str, *args: Any, **kwargs: Any):
        """Открывает файл для чтения/записи (поддерживает encoding и т.п.)"""
        return open(path, mode, *args, **kwargs)

    def remove(self, path: str) -> None:
        """Удаляет файл"""
        os.remove(path)

    def getmtime(self, path: str) -> float:
        """Возвращает время модификации файла (epoch seconds)"""
        return os.path.getmtime(path)

    def getmtime_ns(self, path: str) -> int:
        """Возвращает время модификации файла в наносекундах."""
        return os.stat(path, follow_symlinks=False).st_mtime_ns

    def copystat(self, src: str, dst: str) -> None:
        """Копирует метаданные файла"""
        shutil.copystat(src, dst)

    def copy2(self, src: str, dst: str) -> str:
        """Копирует файл с метаданными (как shutil.copy2)"""
        return shutil.copy2(src, dst)

    def disk_usage(self, path: str) -> Tuple[int, int, int]:
        """Возвращает (total, used, free) в байтах"""
        usage = shutil.disk_usage(path)
        return (usage.total, usage.used, usage.free)

    def replace(self, src: str, dst: str) -> None:
        """Атомарно заменяет dst содержимым src (аналог os.replace)."""
        os.replace(src, dst)

    def create_temp_file(self, directory: str, prefix: str, suffix: str) -> str:
        """Создаёт закрытый уникальный временный файл рядом с назначением."""
        file_descriptor, path = tempfile.mkstemp(
            dir=directory,
            prefix=prefix,
            suffix=suffix,
        )
        os.close(file_descriptor)
        return path

    def fsync_file(self, file_object: IO[Any]) -> None:
        """Сбрасывает пользовательские и системные буферы файла."""
        file_object.flush()
        os.fsync(file_object.fileno())

    def fsync_directory(self, path: str) -> None:
        """Закрепляет атомарную замену в директории назначения."""
        directory_fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
