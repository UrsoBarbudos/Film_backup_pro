"""
`engine.py` — фасад для обратной совместимости.

Исторически весь «движок» жил в одном файле и импортировался как `from engine import ...`.
Чтобы избежать конфликта импорта между файлом `engine.py` и пакетом `engine/`, вся логика
вынесена в пакет `engine_modules/`, а этот модуль оставлен тонким API-слоем (реэкспорт).
"""

from engine_modules.categories import (
    AUDIO_EXTENSIONS,
    CATEGORY_TYPE,
    DATA_EXTENSIONS,
    PHOTO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    get_file_category,
    get_folder_predominant_category,
    is_system_file,
)
from engine_modules.entrypoints import start_backup_process
from engine_modules.scanning import scan_total_size

__all__ = [
    # categories
    "AUDIO_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "PHOTO_EXTENSIONS",
    "DATA_EXTENSIONS",
    "CATEGORY_TYPE",
    "get_file_category",
    "is_system_file",
    "get_folder_predominant_category",
    # scanning
    "scan_total_size",
    # entrypoint
    "start_backup_process",
]
