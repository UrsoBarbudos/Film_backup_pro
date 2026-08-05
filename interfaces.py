"""
Интерфейсы (Protocols) для Dependency Injection.
Определяет контракты для основных зависимостей приложения.
"""

from typing import Protocol, Optional, Dict, List, Tuple, Iterator, IO, Callable, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backup_components.operation_results import CopyResult, VerificationResult


class IConfig(Protocol):
    """Интерфейс для работы с конфигурацией"""
    
    def load(self) -> Dict:
        """Загружает настройки из файла"""
        ...
    
    def save(self, **settings) -> None:
        """Сохраняет настройки в файл"""
        ...
    
    def get(self, key: str, default=None):
        """Получает значение настройки"""
        ...
    
    def set(self, key: str, value) -> None:
        """Устанавливает значение настройки"""
        ...


class IFileSystemInterface(Protocol):
    """Интерфейс для работы с файловой системой"""
    
    def exists(self, path: str) -> bool:
        """Проверяет существование пути"""
        ...
    
    def isfile(self, path: str) -> bool:
        """Проверяет, является ли путь файлом"""
        ...
    
    def isdir(self, path: str) -> bool:
        """Проверяет, является ли путь директорией"""
        ...
    
    def getsize(self, path: str) -> int:
        """Возвращает размер файла в байтах"""
        ...
    
    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        """Создает директорию (рекурсивно)"""
        ...
    
    def walk(self, path: str) -> Iterator[Tuple[str, List[str], List[str]]]:
        """Обходит директорию рекурсивно. Возвращает (dirpath, dirnames, filenames)"""
        ...
    
    def join(self, *paths: str) -> str:
        """Объединяет пути"""
        ...
    
    def basename(self, path: str) -> str:
        """Возвращает базовое имя пути"""
        ...
    
    def dirname(self, path: str) -> str:
        """Возвращает директорию пути"""
        ...
    
    def relpath(self, path: str, start: str) -> str:
        """Возвращает относительный путь от start до path"""
        ...
    
    def open(self, path: str, mode: str, *args: Any, **kwargs: Any) -> IO[Any]:
        """Открывает файл для чтения/записи (поддерживает encoding и т.п.)"""
        ...

    def remove(self, path: str) -> None:
        """Удаляет файл"""
        ...

    def getmtime(self, path: str) -> float:
        """Возвращает время модификации файла (epoch seconds)"""
        ...

    def getmtime_ns(self, path: str) -> int:
        """Возвращает время модификации файла в наносекундах."""
        ...

    def copystat(self, src: str, dst: str) -> None:
        """Копирует метаданные файла"""
        ...

    def copy2(self, src: str, dst: str) -> str:
        """Копирует файл с метаданными (как shutil.copy2)"""
        ...

    def disk_usage(self, path: str) -> Tuple[int, int, int]:
        """Возвращает (total, used, free) в байтах"""
        ...

    def replace(self, src: str, dst: str) -> None:
        """Атомарно заменяет dst содержимым src (аналог os.replace)."""
        ...

    def create_temp_file(self, directory: str, prefix: str, suffix: str) -> str:
        """Создаёт уникальный временный файл в указанной директории."""
        ...

    def fsync_file(self, file_object: IO[Any]) -> None:
        """Сбрасывает буферы открытого файла на физический носитель."""
        ...

    def fsync_directory(self, path: str) -> None:
        """Синхронизирует запись об изменении директории."""
        ...


class IDebugLogger(Protocol):
    """Интерфейс для отладочного логирования"""
    
    def log(
        self,
        location: str,
        message: str,
        data: Optional[Dict] = None,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        hypothesis_id: Optional[str] = None
    ) -> None:
        """Записывает отладочное сообщение в лог файл"""
        ...


class ITelegramClient(Protocol):
    """Контракт клиента Telegram Bot API."""

    def validate_token(self, token: str):
        ...

    def validate_chat_id_format(self, chat_id: str):
        ...

    def send_message(
        self,
        token: str,
        chat_id: str,
        text: str,
        *,
        parse_mode: Optional[str] = None,
    ):
        ...

    def test_connection(self, token: str, chat_id: str):
        ...


class IFileCopier(Protocol):
    """Интерфейс для копирования файлов"""
    
    def copy_file(
        self,
        source_path: str,
        destination_path: str,
        destination_root: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        base_copied_bytes: int = 0,
        total_bytes: int = 0
    ) -> "CopyResult":
        """
        Копирует файл и может вернуть доказательство проверки текущей операции.
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param destination_root: Корневая директория назначения (опционально)
        :param progress_callback: Callback для обновления прогресса (опционально)
        :param base_copied_bytes: Базовое количество скопированных байт для расчета прогресса
        :param total_bytes: Общий объем данных для расчета прогресса
        :return: Структурированный результат копирования
        """
        ...


class IFileVerifier(Protocol):
    """Интерфейс для проверки целостности файлов"""
    
    def verify_file(
        self,
        source_path: str,
        destination_path: str,
        copy_verification_result: Optional[object] = None,
    ) -> "VerificationResult":
        """
        Проверяет целостность скопированного файла
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param copy_verification_result: Доказательство текущей операции или None
        :return: Структурированный результат проверки
        """
        ...
