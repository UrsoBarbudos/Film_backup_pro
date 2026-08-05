from __future__ import annotations

import logging

from interfaces import IFileSystemInterface
from engine_modules.category_definitions import (
    CATEGORY_DEFINITIONS,
    CATEGORY_TYPE,
    DATA_EXTENSIONS,
    DEFAULT_CATEGORY,
)


logger = logging.getLogger(__name__)


VIDEO_EXTENSIONS = next(d.extensions for d in CATEGORY_DEFINITIONS if d.key == "Video")
AUDIO_EXTENSIONS = next(d.extensions for d in CATEGORY_DEFINITIONS if d.key == "Audio")
PHOTO_EXTENSIONS = next(d.extensions for d in CATEGORY_DEFINITIONS if d.key == "Photo")


def get_file_category(filename: str) -> CATEGORY_TYPE:
    """
    Определяет категорию файла по расширению.
    Возвращает: 'Video', 'Audio' или 'Photo'.
    """
    fname = filename.lower().strip()
    for definition in CATEGORY_DEFINITIONS:
        if fname.endswith(definition.extensions):
            return definition.key
    return DEFAULT_CATEGORY


def is_system_file(filename: str) -> bool:
    """
    Проверяет, является ли файл системным файлом macOS.
    Возвращает True для системных файлов, которые следует исключить из резервного копирования.
    """
    fname = filename.lower().strip()

    from source_backup_marker import (
        is_source_backup_marker,
        is_source_backup_marker_temp,
    )

    if is_source_backup_marker(filename) or is_source_backup_marker_temp(filename):
        return True

    system_files = {
        ".ds_store",  # Метаданные папок
        ".trashes",  # Корзина
        ".spotlight-v100",  # Индексы Spotlight
        ".fseventsd",  # Журнал событий файловой системы
        ".vol",  # Метаданные тома
    }

    if fname in system_files:
        return True

    # Ресурсные вилки (resource forks)
    if fname.startswith("._"):
        return True

    return False


def get_folder_predominant_category(
    folder_path: str,
    file_system: IFileSystemInterface,
) -> CATEGORY_TYPE:
    """
    Определяет преобладающую категорию файлов в папке.
    Рекурсивно анализирует содержимое папки и возвращает категорию с наибольшим количеством файлов.
    """
    fs = file_system

    if not fs.exists(folder_path) or not fs.isdir(folder_path):
        return "Video"

    category_counts = {definition.key: 0 for definition in CATEGORY_DEFINITIONS}

    try:
        for _, _, filenames in fs.walk(folder_path):
            for filename in filenames:
                if is_system_file(filename):
                    continue
                category = get_file_category(filename)
                if category in category_counts:
                    category_counts[category] += 1
    except (OSError, PermissionError, FileNotFoundError) as e:
        # В случае ошибки доступа возвращаем Video по умолчанию (сохраняем текущее поведение)
        logger.warning("Ошибка при анализе папки %s: %s", folder_path, e)
        return "Video"

    if sum(category_counts.values()) == 0:
        return "Video"

    predominant_category = max(category_counts.items(), key=lambda x: x[1])[0]
    return predominant_category
