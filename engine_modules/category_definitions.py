"""Каноническое описание категорий файлов и проектных папок."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


CATEGORY_TYPE = Literal["Video", "Audio", "Photo"]
DEFAULT_CATEGORY: CATEGORY_TYPE = "Video"


@dataclass(frozen=True, slots=True)
class CategoryDefinition:
    key: CATEGORY_TYPE
    extensions: tuple[str, ...]


CATEGORY_DEFINITIONS: tuple[CategoryDefinition, ...] = (
    CategoryDefinition(
        key="Video",
        extensions=(
            ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm",
            ".r3d", ".red", ".ari", ".arx", ".mxf", ".mts", ".m2ts",
            ".cin", ".crm",
        ),
    ),
    CategoryDefinition(
        key="Audio",
        extensions=(".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"),
    ),
    CategoryDefinition(
        key="Photo",
        extensions=(".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp", ".heic"),
    ),
)

_DEFINITIONS_BY_KEY = {definition.key: definition for definition in CATEGORY_DEFINITIONS}

# Сохранено как публичная legacy-константа. Категория Data пока не участвует
# в маршрутизации: неизвестные файлы по-прежнему относятся к Video.
DATA_EXTENSIONS = (
    ".csv", ".xls", ".xlsx", ".json", ".xml", ".txt", ".md",
    ".pdf", ".doc", ".docx",
)


def get_category_definition(category: str) -> Optional[CategoryDefinition]:
    return _DEFINITIONS_BY_KEY.get(category)  # type: ignore[arg-type]


def get_category_keys() -> tuple[CATEGORY_TYPE, ...]:
    return tuple(definition.key for definition in CATEGORY_DEFINITIONS)

