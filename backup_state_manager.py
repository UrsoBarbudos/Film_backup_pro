"""
Менеджер состояния процесса резервного копирования.
Отвечает за управление состоянием: источники, назначение.
"""

import os
from typing import Optional, List


def canonicalize_path(path: str) -> str:
    """Канонизирует путь для устойчивого сравнения."""
    normalized = (path or "").strip()
    if not normalized:
        return ""
    normalized = normalized.rstrip("/") or "/"
    normalized = os.path.normpath(normalized)
    try:
        normalized = os.path.realpath(normalized)
    except Exception:
        # Best-effort: сравнение хотя бы по normpath.
        pass
    return normalized


class BackupStateManager:
    """Управляет состоянием процесса резервного копирования"""
    
    def __init__(self):
        """Инициализация менеджера состояния"""
        self._source_paths: List[str] = []
        self._destination_path: Optional[str] = None
        self._source_type_overrides: dict[str, str] = {}
    
    @property
    def source_paths(self) -> List[str]:
        """Возвращает список путей источников"""
        return self._source_paths.copy()
    
    @property
    def destination_path(self) -> Optional[str]:
        """Возвращает путь назначения"""
        return self._destination_path

    @staticmethod
    def canonicalize_path(path: str) -> str:
        """Совместимый доступ к общей функции канонизации."""
        return canonicalize_path(path)

    def _find_existing_source_path(self, path: str) -> Optional[str]:
        """Находит фактически хранимый путь по точному или каноническому совпадению."""
        if path in self._source_paths:
            return path
        target_canon = self.canonicalize_path(path)
        if not target_canon:
            return None
        for existing in self._source_paths:
            if self.canonicalize_path(existing) == target_canon:
                return existing
        return None

    def resolve_source_path(self, path: str) -> Optional[str]:
        """Публично возвращает фактически сохранённый путь источника."""
        return self._find_existing_source_path(path)
    
    def has_sources(self) -> bool:
        """Проверяет наличие источников"""
        return len(self._source_paths) > 0
    
    def has_destination(self) -> bool:
        """Проверяет наличие назначения"""
        return self._destination_path is not None
    
    def set_source_paths(self, paths: List[str]):
        """Устанавливает список путей источников"""
        self._source_paths = paths.copy() if paths else []
    
    def add_source_path(self, path: str) -> bool:
        """
        Добавляет путь источника
        
        :param path: Путь к источнику
        :return: True если добавлен, False если уже существует
        """
        if self._find_existing_source_path(path) is None:
            self._source_paths.append(path)
            return True
        return False
    
    def remove_source_path(self, path: str) -> bool:
        """
        Удаляет путь источника
        
        :param path: Путь к источнику
        :return: True если удален, False если не найден
        """
        existing_path = self._find_existing_source_path(path)
        if existing_path is not None:
            self._source_paths.remove(existing_path)
            self._source_type_overrides.pop(existing_path, None)
            return True
        return False

    def set_source_type(self, path: str, source_type: str) -> bool:
        """
        Устанавливает пользовательский тип источника.

        :return: True если источник найден и тип сохранён.
        """
        existing_path = self._find_existing_source_path(path)
        normalized_type = (source_type or "").strip().lower()
        if existing_path is None or not normalized_type:
            return False
        self._source_type_overrides[existing_path] = normalized_type
        return True

    def get_source_type(self, path: str) -> Optional[str]:
        """Возвращает пользовательский тип источника, если задан."""
        existing_path = self._find_existing_source_path(path)
        if existing_path is None:
            return None
        return self._source_type_overrides.get(existing_path)

    def remove_source_type(self, path: str) -> bool:
        """Удаляет пользовательский тип источника."""
        existing_path = self._find_existing_source_path(path)
        if existing_path is None:
            return False
        return self._source_type_overrides.pop(existing_path, None) is not None
    
    def set_destination_path(self, path: Optional[str]):
        """Устанавливает путь назначения"""
        self._destination_path = path
    
    def clear_all(self):
        """Очищает все состояние"""
        self._source_paths.clear()
        self._destination_path = None
        self._source_type_overrides.clear()
    
    def clear_sources(self):
        """Очищает только источники"""
        self._source_paths.clear()
        self._source_type_overrides.clear()
    
    def clear_destination(self):
        """Очищает только назначение"""
        self._destination_path = None
