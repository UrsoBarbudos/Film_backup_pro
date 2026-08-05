"""
Controller (presenter) для главного окна.

Задачи:
- держит orchestration UI-событий (выбор/добавление источников, назначение, enable/disable кнопки);
- подписывается на результаты фонового расчёта размеров;
- не содержит прямых ссылок на UI-виджеты (работает через тонкий интерфейс View).
"""

from __future__ import annotations

import logging
from typing import List, Optional, Protocol

from interfaces import IConfig, IFileSystemInterface, IDebugLogger
from backup_state_manager import (
    BackupStateManager,
    canonicalize_path as canonicalize_path_for_compare,
)
from source_manager import SourceManager
from ui.file_selection_handler import FileSelectionHandler
from ui.main_window_view_model import MainWindowViewModel
from ui.source_size_service import SourceSizeService
from notifications import NotificationManager
from source_backup_marker import SourceBackupMarkerService

logger = logging.getLogger(__name__)


class IMainWindowView(Protocol):
    def render_add_source(self, source_path: str, *, size_bytes: int, source_type: str | None = None) -> None: ...
    def render_remove_source(self, source_path: str) -> None: ...
    def render_sources(self, source_paths: List[str]) -> None: ...
    def render_source_size(self, source_path: str, *, size_bytes: int) -> None: ...
    def render_source_type(self, source_path: str, *, source_type: str) -> None: ...
    def render_total_size(self, *, total_size_bytes: int) -> None: ...
    def render_destination(self, destination_path: str) -> None: ...
    def render_disk_info_refresh(self) -> None: ...
    def render_destination_exceeded(self, *, is_exceeded: bool) -> None: ...
    def render_start_enabled(self, *, enabled: bool) -> None: ...
    def set_last_destination_dir(self, path: str) -> None: ...
    def set_last_source_dir(self, path: str) -> None: ...
    def render_user_message(self, message: str, *, kind: str) -> None: ...
    def confirm_previously_backed_up_source(self, marker) -> bool: ...


class MainWindowController:
    def __init__(
        self,
        *,
        view: IMainWindowView,
        state_manager: BackupStateManager,
        source_manager: SourceManager,
        view_model: MainWindowViewModel,
        file_selection_handler: FileSelectionHandler,
        size_service: SourceSizeService,
        config: IConfig,
        file_system: IFileSystemInterface,
        debug_logger: Optional[IDebugLogger] = None,
        source_backup_marker_service: Optional[SourceBackupMarkerService] = None,
    ) -> None:
        self._view = view
        self._state_manager = state_manager
        self._source_manager = source_manager
        self._view_model = view_model
        self._file_selection_handler = file_selection_handler
        self._size_service = size_service
        self._config = config
        self._file_system = file_system
        self._debug_logger = debug_logger
        self._source_backup_marker_service = (
            source_backup_marker_service or SourceBackupMarkerService()
        )

        # Создаем NotificationManager для отправки системных уведомлений
        settings = self._config.load()
        macos_notifications_enabled = settings.get('macos_notifications_enabled', True)
        self._notification_manager = NotificationManager(
            macos_notifications_enabled=macos_notifications_enabled
        )

        self._size_service.size_ready.connect(self._on_size_ready)

    def add_sources(self, paths: List[str]) -> None:
        added_paths, duplicate_paths = self._file_selection_handler.handle_drop_sources(
            paths,
            before_add=self._allow_source_addition,
        )
        
        # Обрабатываем успешно добавленные источники
        for path in added_paths:
            cached_size = self._source_manager.get_cached_size(path)
            source_type = self._resolve_effective_source_type(path)
            self._view.render_add_source(
                path,
                size_bytes=cached_size if cached_size is not None else 0,
                source_type=source_type,
            )

            if cached_size is None:
                self._size_service.start(path)
        
        # Отправляем уведомление о дубликатах, если они есть
        if duplicate_paths:
            if len(duplicate_paths) == 1:
                message = f"Источник уже добавлен:\n{duplicate_paths[0]}"
            else:
                message = f"Источники уже добавлены:\n" + "\n".join(duplicate_paths)
            
            self._notification_manager.send_simple_notification(
                title="Источник уже добавлен",
                message=message
            )

        self._refresh_after_state_change()

    def remove_source(self, source_path: str) -> None:
        resolved_source_path = self._state_manager.resolve_source_path(source_path) or source_path
        self._size_service.cancel(resolved_source_path)

        removed = self._state_manager.remove_source_path(resolved_source_path)
        if not removed:
            logger.warning("Не удалось удалить источник: %s", source_path)
            return

        self._source_manager.remove_source_size(resolved_source_path)
        self._source_manager.remove_folder_category(resolved_source_path)
        self._view.render_remove_source(resolved_source_path)

        self._refresh_after_state_change()

    def set_source_type(self, source_path: str, source_type: str) -> None:
        """
        Сохраняет пользовательский тип источника и обновляет карточку.
        """
        resolved_source_path = self._state_manager.resolve_source_path(source_path)
        if resolved_source_path is None:
            logger.warning("Источник не найден для смены типа: %s", source_path)
            return
        changed = self._state_manager.set_source_type(resolved_source_path, source_type)
        if not changed:
            logger.warning("Не удалось сохранить тип '%s' для источника: %s", source_type, source_path)
            return
        effective_type = self._resolve_effective_source_type(resolved_source_path)
        self._view.render_source_type(resolved_source_path, source_type=effective_type)

    def set_destination(self, destination_path: str) -> None:
        self._state_manager.set_destination_path(destination_path)
        self._view.render_destination(destination_path)

        # Сохраняем last_destination_dir (нужно для последующих открытий диалога).
        last_destination_dir = destination_path
        self._view.set_last_destination_dir(last_destination_dir)
        self._config.save(last_destination_dir=last_destination_dir)

        self._refresh_after_state_change()

    def on_selected_source_dialog(self, selected_path: str) -> None:
        """
        Обработчик для выбора источника через диалог (App остаётся владельцем диалога).
        """
        added, duplicate_path = self._file_selection_handler.handle_select_source(
            selected_path,
            before_add=self._allow_source_addition,
        )
        if added:
            cached_size = self._source_manager.get_cached_size(selected_path)
            source_type = self._resolve_effective_source_type(selected_path)
            self._view.render_add_source(
                selected_path,
                size_bytes=cached_size if cached_size is not None else 0,
                source_type=source_type,
            )
            if cached_size is None:
                self._size_service.start(selected_path)
        elif duplicate_path:
            # Отправляем уведомление о дубликате
            self._notification_manager.send_simple_notification(
                title="Источник уже добавлен",
                message=f"Источник уже добавлен:\n{duplicate_path}"
            )

        # Обновляем last_source_dir и сохраняем.
        parent_dir = self._file_system.dirname(selected_path)
        last_source_dir = parent_dir if parent_dir else selected_path
        self._view.set_last_source_dir(last_source_dir)
        self._config.save(last_source_dir=last_source_dir)

        self._refresh_after_state_change()

    def _allow_source_addition(self, source_path: str) -> bool:
        """Проверяет отметку после валидации пути, но до изменения BackupStateManager."""
        marker = self._source_backup_marker_service.read_latest(source_path)
        if marker is None:
            return True
        settings = self._config.load()
        if not settings.get("warn_on_previously_backed_up_source", True):
            logger.info("Найдена валидная отметка backup на источнике %s", source_path)
            return True
        return self._view.confirm_previously_backed_up_source(marker)

    def recompute_ui_state(self) -> None:
        """
        Пересчитывает состояние UI: exceeded state и enabled/disabled start.

        Важно: disk-space проверка должна выполняться всегда, чтобы сбрасывать exceeded
        при удалении источников.
        """
        has_sources = self._state_manager.has_sources()
        has_destination = self._state_manager.has_destination()

        disk_ok = True
        if has_sources and has_destination:
            is_sufficient, _free, _total, _required = self._view_model.get_disk_space_info(self._file_system)
            self._view.render_destination_exceeded(is_exceeded=not is_sufficient)
            disk_ok = bool(is_sufficient)
        else:
            self._view.render_destination_exceeded(is_exceeded=False)

        basic_ok = self._view_model.has_basic_conditions()
        can_start = bool(basic_ok and disk_ok)
        self._view.render_start_enabled(enabled=can_start)

    def shutdown(self) -> None:
        """
        Вызывать при закрытии окна/очистке формы, чтобы мягко отменить все задачи.
        """
        self._size_service.cancel_all()

    def _refresh_after_state_change(self) -> None:
        self._view.render_total_size(total_size_bytes=self._source_manager.get_total_sources_size())
        if self._state_manager.has_destination():
            self._view.render_disk_info_refresh()
        self.recompute_ui_state()

    def _on_size_ready(self, source_path: str, size_bytes_str: str) -> None:
        try:
            size_bytes = int(size_bytes_str)
        except (TypeError, ValueError):
            size_bytes = 0

        if size_bytes < 0:
            size_bytes = 0

        self._view.render_source_size(source_path, size_bytes=size_bytes)
        self._refresh_after_state_change()

    def _resolve_effective_source_type(self, source_path: str) -> str:
        override_type = self._state_manager.get_source_type(source_path)
        return self._source_manager.get_effective_source_type(source_path, override_type=override_type)
