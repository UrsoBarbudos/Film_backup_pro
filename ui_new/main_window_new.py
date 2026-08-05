"""
Главное окно приложения Dублёр (PySide6) — новый UI (тестовое полотно).
Точка входа: main_new_ui.py
"""

import os
import sys
import logging
import warnings
from datetime import datetime
from typing import Optional, Dict, List, Tuple


try:
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QStackedWidget,
        QFileDialog, QMessageBox, QGraphicsOpacityEffect
    )
    from PySide6.QtCore import QTimer, QSize, QPropertyAnimation, QEasingCurve, QRect, Qt
    from PySide6.QtGui import QKeySequence, QShortcut

    from widgets import SourceItem
    from composition import AppContext, build_app_context
    from interfaces import IFileSystemInterface
    from themes import ThemeManager
    from backup_state_manager import BackupStateManager
    from source_manager import SourceManager
    from backup_launcher import BackupStarter
    from backup_process_controller import BackupProcessController
    from ui.main_window_view_model import MainWindowViewModel
    from ui.main_window_controller import MainWindowController
    from ui.source_size_service import SourceSizeService
    from ui.file_selection_handler import FileSelectionHandler
    from ui_new.components import (
        TopButtonsWidget,
        SourcesHeaderAndDropWidget,
        SourcesCardsWidget,
        SourceCardSlideWrapper,
        DestinationSectionWidget,
        ButtonsSectionWidget,
    )
    from ui_new.components.sources_cards_widget import ANIMATION_DURATION_MS
    from ui.ui_constants import UISpacing, UIMargins, UISizes, UIAnimation, main_window_content_height, cards_area_height
    from previously_backed_up_source_dialog_handler import PreviouslyBackedUpSourceDialogHandler

except Exception as e:
    print(f"ERROR: Import failed: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)


logger = logging.getLogger(__name__)


class AppNew(QMainWindow):
    """Главное окно приложения Dублёр (новый UI)"""

    APP_VERSION = "1.21.1"
    APP_AUTHOR = "@Urso_barbudos"
    GREEN_BUTTON_COLOR = "#2FA572"

    def __init__(
        self,
        context: Optional["AppContext"] = None,
        file_system: Optional[IFileSystemInterface] = None,
    ):
        logger.info("Инициализация приложения Dублёр (PySide6, новый UI)...")

        if context is None:
            context = build_app_context()

        self.file_system = file_system or context.file_system
        self.debug_logger = context.debug_logger
        self.telegram_client = context.telegram_client
        self.source_backup_marker_service = context.source_backup_marker_service

        try:
            super().__init__()

            self.state_manager = BackupStateManager()
            self.source_manager = SourceManager(file_system=self.file_system)
            self.view_model = MainWindowViewModel(
                state_manager=self.state_manager,
                source_manager=self.source_manager
            )
            self.file_selection_handler = FileSelectionHandler(
                state_manager=self.state_manager,
                source_manager=self.source_manager
            )
            self.backup_starter = BackupStarter(app_instance=self)
            self.backup_controller = BackupProcessController(
                app_instance=self,
                backup_starter=self.backup_starter,
                state_manager=self.state_manager,
                source_manager=self.source_manager
            )
            self.previously_backed_up_source_dialog_handler = (
                PreviouslyBackedUpSourceDialogHandler()
            )

            self._select_sources_in_progress = False
            self._last_dialog_close_time = 0
            self._source_items: Dict[str, SourceItem] = {}
            self._add_source_pending_queue: List[Tuple[str, int, Optional[str]]] = []
            self._add_source_phase: str = "idle"
            self._add_source_pending_after_phase1: Optional[Tuple[str, int, Optional[str]]] = None
            self._window_height_animation: Optional[QPropertyAnimation] = None
            self._window_target_height: Optional[int] = None
            self._remove_source_pending_queue: List[str] = []
            self._remove_source_phase: str = "idle"
            self._transition_fade_effect: Optional[QGraphicsOpacityEffect] = None
            self._transition_fade_animation: Optional[QPropertyAnimation] = None
            self._transition_resize_animation: Optional[QPropertyAnimation] = None
            self._saved_geometry_before_transition: Optional[QRect] = None
            self._is_transitioning: bool = False

            self.config = context.config
            settings = self.config.load()

            self.last_source_dir = settings.get('last_source_dir')
            self.last_destination_dir = settings.get('last_destination_dir')
            self.prevent_sleep = settings.get('prevent_sleep', True)
            self.theme = settings.get('theme', 'light')
            self.create_md_log = settings.get('create_md_log', False)
            self.verification_mode = settings.get('verification_mode', 'full')

            self.setWindowTitle(f"Dублёр v{self.APP_VERSION}")
            initial_height = main_window_content_height(0)
            self.resize(550, initial_height)
            self.setMinimumSize(550, initial_height)
            self._center_window()

            self._create_ui()

            self.size_service = SourceSizeService(
                source_manager=self.source_manager,
                debug_logger=self.debug_logger,
                parent=self,
            )
            self.controller = MainWindowController(
                view=self,
                state_manager=self.state_manager,
                source_manager=self.source_manager,
                view_model=self.view_model,
                file_selection_handler=self.file_selection_handler,
                size_service=self.size_service,
                config=self.config,
                file_system=self.file_system,
                debug_logger=self.debug_logger,
                source_backup_marker_service=context.source_backup_marker_service,
            )

            self._apply_theme()
            self.check_button_state()

            logger.info("Приложение (новый UI) готово к работе.")
        except Exception as e:
            if hasattr(self, 'debug_logger'):
                import traceback
                self.debug_logger.log(
                    location="main_window_new.py:AppNew.__init__",
                    message="EXCEPTION in AppNew.__init__()",
                    data={"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()},
                    hypothesis_id="A,C,D,E"
                )
            logger.exception("Failed to initialize AppNew: %s", e)
            import traceback
            traceback.print_exc()
            raise

    def _center_window(self):
        frame = self.frameGeometry()
        screen = self.screen().availableGeometry().center()
        frame.moveCenter(screen)
        self.move(frame.topLeft())

    def _apply_theme(self):
        self.setStyleSheet(ThemeManager.get_main_window_stylesheet(self.theme))
        if hasattr(self, 'sources_header'):
            self.sources_header.update_theme(self.theme)
        if hasattr(self, 'destination_section'):
            self.destination_section.update_theme(self.theme)
        if hasattr(self, 'sources_list_layout'):
            for i in range(self.sources_list_layout.count()):
                item = self.sources_list_layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if isinstance(widget, SourceCardSlideWrapper):
                        card = widget.source_item
                        card.theme = self.theme
                        card._apply_theme_styles()
                    elif isinstance(widget, SourceItem):
                        widget.theme = self.theme
                        widget._apply_theme_styles()
    def _create_ui(self):
        try:
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            main_layout = QVBoxLayout(central_widget)
            main_layout.setContentsMargins(*UIMargins.MAIN_LAYOUT)
            main_layout.setSpacing(0)

            self.stacked = QStackedWidget(central_widget)
            main_layout.addWidget(self.stacked)

            self.main_page = QWidget(self.stacked)
            self.stacked.addWidget(self.main_page)
            main_page_layout = QVBoxLayout(self.main_page)
            main_page_layout.setContentsMargins(0, 0, 0, 0)
            main_page_layout.setSpacing(0)

            self.top_buttons = TopButtonsWidget(self.main_page, app_instance=self)
            self.sources_header = SourcesHeaderAndDropWidget(self.main_page, app_instance=self)
            self.sources_cards = SourcesCardsWidget(self.main_page, app_instance=self)
            self.destination_section = DestinationSectionWidget(self.main_page, app_instance=self)
            self.buttons_section = ButtonsSectionWidget(self.main_page, app_instance=self)
            self._start_shortcuts = [
                QShortcut(QKeySequence(Qt.Key.Key_Return), self.main_page),
                QShortcut(QKeySequence(Qt.Key.Key_Enter), self.main_page),
            ]
            for shortcut in self._start_shortcuts:
                shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
                shortcut.activated.connect(self._start_backup_from_shortcut)

            main_page_layout.addWidget(self.top_buttons)
            self._top_to_sources_spacer = QWidget(self.main_page)
            self._top_to_sources_spacer.setFixedHeight(UISpacing.TOP)
            main_page_layout.addWidget(self._top_to_sources_spacer)
            main_page_layout.addWidget(self.sources_header)
            main_page_layout.addWidget(self.sources_cards)
            self._cards_to_destination_spacer = QWidget(self.main_page)
            self._cards_to_destination_spacer.setFixedHeight(UISpacing.SECTION * 2)
            main_page_layout.addWidget(self._cards_to_destination_spacer)
            main_page_layout.addWidget(self.destination_section)
            main_page_layout.addWidget(self.buttons_section)

            from settings_window import SettingsPage
            from progress_window import ProgressPage
            self.settings_page = SettingsPage(self.stacked, self, on_close=self.show_main_page)
            self.progress_page = ProgressPage(
                self.stacked,
                self,
                on_close=self.reset_after_backup,
            )
            self.stacked.addWidget(self.settings_page)
            self.stacked.addWidget(self.progress_page)
            self.stacked.setCurrentWidget(self.main_page)

            self._setup_backward_compatibility()
            self._window_height_animation = QPropertyAnimation(self, b"size")
            self._window_height_animation.setDuration(ANIMATION_DURATION_MS)
            self._window_height_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self._window_height_animation.finished.connect(self._on_window_height_animation_finished)
            self.sources_cards.height_animation_finished.connect(self._on_cards_height_animation_finished)
            self.sources_cards.animated_height_changed.connect(self._on_cards_animated_height_changed)
            self.render_total_size(total_size_bytes=0)
            self._update_window_min_height()
        except Exception as e:
            import traceback
            logger.exception("Failed to create UI: %s", e)
            traceback.print_exc()
            raise

    def _update_window_min_height(self) -> None:
        """Высота окна по контенту: блоки «магнитятся» к карточкам, мин. высота = контент."""
        count = len(getattr(self, "_source_items", {}))
        content_h = self._content_height_for_cards(count)
        self.setMinimumHeight(content_h)
        if self.height() > content_h:
            self.resize(self.width(), content_h)

    def _on_window_height_animation_finished(self) -> None:
        """После анимации высоты окна фиксируем минимальную высоту."""
        if self._window_target_height is not None:
            self.setMinimumHeight(self._window_target_height)
            self._window_target_height = None

    def _start_window_height_animation(self, content_h: int) -> None:
        """Запустить анимацию высоты окна до content_h."""
        self._window_target_height = content_h
        self._window_height_animation.stop()
        self._window_height_animation.setStartValue(self.size())
        self._window_height_animation.setEndValue(QSize(self.width(), content_h))
        self._window_height_animation.start()

    def _on_cards_animated_height_changed(self, cards_height: int) -> None:
        """Высота зоны карточек изменилась: синхронно подстраиваем высоту окна (при добавлении phase1 или при удалении shrinking) — один источник правды, без подрагивания."""
        if self._add_source_phase != "phase1" and self._remove_source_phase != "shrinking":
            return
        fixed_part = (
            self._content_height_for_cards(0)
            - cards_area_height(0)
        )
        new_h = fixed_part + cards_height
        if self._remove_source_phase == "shrinking":
            self.setMinimumHeight(new_h)
        self.resize(self.width(), new_h)

    def _process_add_source_queue(self) -> None:
        """Обработать очередь добавления источников: запустить фазу 1 для следующего или выйти."""
        if not self._add_source_pending_queue or self._add_source_phase != "idle":
            return
        path, size_bytes, source_type = self._add_source_pending_queue.pop(0)
        self._add_source_pending_after_phase1 = (path, size_bytes, source_type)
        self._add_source_phase = "phase1"
        new_count = len(self._source_items) + 1
        self.sources_cards.update_height(new_count)

    def _on_cards_height_animation_finished(self) -> None:
        """Фаза 1 добавления завершена: вставить карточку с slide-in. Либо анимация удаления завершена: зафиксировать мин. высоту и обработать очередь."""
        if self._remove_source_phase == "shrinking":
            self.setMinimumHeight(self._content_height_for_cards(len(self._source_items)))
            self._remove_source_phase = "idle"
            self._process_remove_source_queue()
            return
        if self._add_source_phase != "phase1" or self._add_source_pending_after_phase1 is None:
            return
        new_count = len(self._source_items) + 1
        self.setMinimumHeight(self._content_height_for_cards(new_count))
        path, size_bytes, source_type = self._add_source_pending_after_phase1
        self._add_source_pending_after_phase1 = None
        self._add_source_phase = "phase2"
        # К моменту появления карточки worker мог уже посчитать размер — берём из кэша, иначе из очереди (исправляет race: size_ready приходит до добавления карточки в _source_items).
        cached_size = self.source_manager.get_cached_size(path) if hasattr(self, "source_manager") else None
        size_to_show = (cached_size if cached_size is not None else size_bytes)
        source_item = SourceItem(
            path,
            self,
            self.sources_list_widget,
            size_bytes=size_to_show,
            source_type=source_type,
        )
        source_item.remove_requested.connect(self.remove_source)
        source_item.source_type_changed.connect(self._on_source_type_changed)
        wrapper = SourceCardSlideWrapper(source_item, parent=self.sources_list_widget)
        count = self.sources_list_layout.count()
        insert_index = max(0, count - 1)
        self.sources_list_layout.insertWidget(insert_index, wrapper)
        self._source_items[self._source_key(path)] = source_item
        wrapper.slide_finished.connect(self._on_source_slide_finished)
        # Запускаем скролл для карточек 6+
        QTimer.singleShot(0, lambda: self._start_card_animations(wrapper))

    def _start_card_animations(self, wrapper: SourceCardSlideWrapper) -> None:
        """Выполнить скролл для карточек 7+ и эмитировать сигнал завершения."""
        card_count = len(self._source_items)
        
        # Для карточек 7+ делаем плавный скролл на высоту одной карточки, чтобы показать новую карточку
        if card_count > UISizes.CARDS_VISIBLE_COUNT:
            # Прокручиваем на высоту одной карточки с учетом spacing
            one_card_height = UISizes.SOURCE_ITEM_HEIGHT + UISizes.CARDS_LIST_SPACING
            current_scroll = self.sources_cards._internal_vbar.value()
            target_scroll = current_scroll + one_card_height
            
            # Запускаем анимированную прокрутку на высоту одной карточки
            self.sources_cards._scroll_animation.stop()
            self.sources_cards._scroll_animation.setStartValue(current_scroll)
            self.sources_cards._scroll_animation.setEndValue(target_scroll)
            self.sources_cards._scroll_animation.start()
        
        # Эмитируем сигнал завершения (раз анимации нет), чтобы обработать следующие карточки
        wrapper.slide_finished.emit()

    def _on_source_slide_finished(self) -> None:
        """Slide-in карточки завершён: обновить высоту окна и обработать очередь."""
        self._add_source_phase = "idle"
        self._update_window_min_height()
        # Скролл теперь запускается вместе с slide-in (см. _start_card_appearance)
        self._process_add_source_queue()

    def _setup_backward_compatibility(self):
        self.settings_button = self.top_buttons.settings_button
        self.clear_all_button = self.top_buttons.clear_all_button
        self.sources_drop = self.sources_header.sources_drop
        self.total_size_label = self.sources_header.total_size_label
        self.sources_list_widget = self.sources_cards.sources_list_widget
        self.sources_list_layout = self.sources_cards.sources_list_layout
        self.destination_widget = self.destination_section.destination_widget
        self.start_button = self.buttons_section.start_button

    def _content_height_for_cards(self, card_count: int) -> int:
        return main_window_content_height(card_count)

    def _sync_window_height_to_current_content(self) -> None:
        content_h = self._content_height_for_cards(len(getattr(self, "_source_items", {})))
        self.setMinimumHeight(content_h)
        self.resize(self.width(), content_h)

    def _set_destination_path(self, path: str):
        self.destination_widget.set_path(path)

    def on_drop_sources(self, paths):
        if hasattr(self, "controller"):
            self.controller.add_sources(list(paths))

    def on_drop_destination(self, path):
        if hasattr(self, "controller"):
            self.controller.set_destination(path)

    def remove_source(self, source_path: str):
        if hasattr(self, "controller"):
            self.controller.remove_source(source_path)

    def _on_source_type_changed(self, source_path: str, source_type: str) -> None:
        if hasattr(self, "controller"):
            self.controller.set_source_type(source_path, source_type)

    def set_last_destination_dir(self, path: str) -> None:
        self.last_destination_dir = path

    def set_last_source_dir(self, path: str) -> None:
        self.last_source_dir = path

    def render_sources(self, source_paths):
        self._add_source_pending_queue.clear()
        self._add_source_phase = "idle"
        self._add_source_pending_after_phase1 = None
        self._remove_source_pending_queue.clear()
        self._remove_source_phase = "idle"
        while self.sources_list_layout.count() > 1:
            item = self.sources_list_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()
        self._source_items.clear()
        for source_path in source_paths:
            cached_size = self.source_manager.get_cached_size(source_path)
            self.render_add_source(
                source_path,
                size_bytes=cached_size if cached_size is not None else 0,
                source_type=self._get_effective_source_type(source_path),
                animated=False,
            )
        self.sources_cards.update_height(len(source_paths))
        self._update_window_min_height()

    def render_add_source(
        self,
        source_path: str,
        *,
        size_bytes: int,
        source_type: Optional[str] = None,
        animated: bool = True
    ) -> None:
        source_key = self._source_key(source_path)
        if source_key in self._source_items:
            return
        if not animated:
            source_item = SourceItem(
                source_path,
                self,
                self.sources_list_widget,
                size_bytes=size_bytes,
                source_type=source_type,
            )
            source_item.remove_requested.connect(self.remove_source)
            source_item.source_type_changed.connect(self._on_source_type_changed)
            count = self.sources_list_layout.count()
            insert_index = max(0, count - 1)
            self.sources_list_layout.insertWidget(insert_index, source_item)
            self._source_items[source_key] = source_item
            self.sources_cards.update_height(len(self._source_items))
            self._update_window_min_height()
            return
        self._add_source_pending_queue.append((source_path, size_bytes, source_type))
        self._process_add_source_queue()

    def render_remove_source(self, source_path: str) -> None:
        source_key = self._source_key(source_path)
        source_item = self._source_items.get(source_key)
        if source_item is None:
            return
        wrapper = source_item.parent()
        if not isinstance(wrapper, SourceCardSlideWrapper):
            self._source_items.pop(source_key, None)
            self.sources_list_layout.removeWidget(source_item)
            source_item.setParent(None)
            source_item.deleteLater()
            self.sources_cards.update_height(len(self._source_items))
            self._update_window_min_height()
            return
        if source_key in self._remove_source_pending_queue:
            return
        self._remove_source_pending_queue.append(source_key)
        self._process_remove_source_queue()

    def _process_remove_source_queue(self) -> None:
        """Обработать очередь удаления: запустить slide-out для следующего или выйти."""
        if self._remove_source_phase != "idle" or not self._remove_source_pending_queue:
            return
        path = self._remove_source_pending_queue.pop(0)
        source_item = self._source_items.get(path)
        if source_item is None:
            self._process_remove_source_queue()
            return
        wrapper = source_item.parent()
        if not isinstance(wrapper, SourceCardSlideWrapper):
            self._process_remove_source_queue()
            return
        self._remove_source_phase = "sliding_out"
        wrapper.slide_finished.connect(
            lambda p=path: self._on_remove_slide_finished(p)
        )
        wrapper.start_slide_out()

    def _ensure_cards_layout_only_stretch(self) -> None:
        """Оставить в layout только stretch (удалить все виджеты карточек). Вызывать при 0 карточек."""
        layout = self.sources_list_layout
        i = 0
        while i < layout.count():
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
                continue
            i += 1

    def _on_remove_slide_finished(self, source_path: str) -> None:
        """Slide-out завершён: удалить виджет, сжать зону и окно, обработать очередь."""
        source_item = self._source_items.pop(source_path, None)
        if source_item is None:
            self._remove_source_phase = "idle"
            self._process_remove_source_queue()
            return
        wrapper = source_item.parent()
        if wrapper is not None:
            self.sources_list_layout.removeWidget(wrapper)
            wrapper.setParent(None)
            wrapper.deleteLater()
        new_count = len(self._source_items)
        self._remove_source_phase = "shrinking"
        self.sources_cards.update_height(new_count)
        if new_count == 0:
            self._ensure_cards_layout_only_stretch()
        # Окно подстраивается по кадрам в _on_cards_animated_height_changed; по окончании анимации — в _on_cards_height_animation_finished

    def render_source_size(self, source_path: str, *, size_bytes: int) -> None:
        widget = self._source_items.get(self._source_key(source_path))
        if widget is None:
            return
        widget.update_size(size_bytes)

    def render_source_type(self, source_path: str, *, source_type: str) -> None:
        widget = self._source_items.get(self._source_key(source_path))
        if widget is None:
            return
        widget.update_source_type(source_type)

    def render_total_size(self, *, total_size_bytes: int) -> None:
        from utils import format_size
        self.total_size_label.setText(f"Общий объём: {format_size(total_size_bytes)}")

    def render_destination(self, destination_path: str) -> None:
        self._set_destination_path(destination_path)

    def render_user_message(self, message: str, *, kind: str) -> None:
        kind_norm = (kind or "").strip().lower()
        text = (message or "").strip() or "(пустое сообщение)"
        theme = getattr(self, "theme", "light") or "light"
        is_dark = str(theme).strip().lower() == "dark"
        if is_dark:
            bg, fg = "#2b2b2b", "#FAFAFA"
            btn_bg, btn_hover, btn_border = "#555", "#666", "#555"
        else:
            bg, fg = "#FAFAFA", "#000000"
            btn_bg, btn_hover, btn_border = "#999", "#888", "#ddd"
        box = QMessageBox(self)
        box.setStyleSheet(
            f"""
            QMessageBox {{ background-color: {bg}; }}
            QMessageBox QLabel {{ color: {fg}; font-size: 14px; background-color: transparent; }}
            QMessageBox QPushButton {{ background-color: {btn_bg}; color: #FAFAFA; border: 1px solid {btn_border}; border-radius: 4px; padding: 6px 12px; min-width: 80px; }}
            QMessageBox QPushButton:hover {{ background-color: {btn_hover}; }}
            """
        )
        if kind_norm == "error":
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("Ошибка")
        elif kind_norm == "info":
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("Информация")
        else:
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Внимание")
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def confirm_previously_backed_up_source(self, marker) -> bool:
        return self.previously_backed_up_source_dialog_handler.confirm(marker, self)

    def render_disk_info_refresh(self) -> None:
        self.destination_widget.update_disk_info()

    def render_destination_exceeded(self, *, is_exceeded: bool) -> None:
        self.destination_widget.set_exceeded_state(is_exceeded)

    def render_start_enabled(self, *, enabled: bool) -> None:
        if enabled:
            self._enable_start_button()
        else:
            self._disable_start_button()

    def _clear_all_fields(self):
        if hasattr(self, "controller"):
            self.controller.shutdown()
        self.state_manager.clear_all()
        self.source_manager.clear_cache()
        self.destination_widget.set_path("")
        self.destination_widget.set_exceeded_state(False)
        self.render_sources([])
        self.render_total_size(total_size_bytes=0)
        self.check_button_state()

    def select_sources(self):
        if self._select_sources_in_progress:
            return
        self._select_sources_in_progress = True
        try:
            from utils import validate_path
            initial_dir = self.last_source_dir if (self.last_source_dir and validate_path(self.last_source_dir, file_system=self.file_system)) else ("/Volumes" if sys.platform == 'darwin' else "/")
            selected_path = QFileDialog.getExistingDirectory(self, "Выберите папку-источник", initial_dir)
            if selected_path and hasattr(self, "controller"):
                self.controller.on_selected_source_dialog(selected_path)
        finally:
            import time
            self._last_dialog_close_time = time.time()
            QTimer.singleShot(300, lambda: setattr(self, '_select_sources_in_progress', False))

    def select_destination(self):
        from utils import validate_path
        initial_dir = self.last_destination_dir if (self.last_destination_dir and validate_path(self.last_destination_dir, file_system=self.file_system)) else (os.path.expanduser("~") if sys.platform == 'darwin' else "/")
        selected_path = QFileDialog.getExistingDirectory(self, "Выберите папку назначения", initial_dir)
        if selected_path and hasattr(self, "controller"):
            self.controller.set_destination(selected_path)

    def check_button_state(self):
        if hasattr(self, "controller"):
            self.controller.recompute_ui_state()

    def _source_key(self, source_path: str) -> str:
        if hasattr(self, "state_manager"):
            return self.state_manager.canonicalize_path(source_path)
        return source_path

    def _get_effective_source_type(self, source_path: str) -> str:
        override_type = self.state_manager.get_source_type(source_path)
        return self.source_manager.get_effective_source_type(source_path, override_type=override_type)

    def _enable_start_button(self):
        self.start_button.setEnabled(True)
        self.start_button.setStyleSheet(f"background-color: {ThemeManager.get_green_button_color()}; color: #FAFAFA;")

    def _disable_start_button(self):
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet(f"background-color: {ThemeManager.get_red_button_color_with_opacity()}; color: #FAFAFA;")

    def _start_backup_from_shortcut(self) -> None:
        """Запустить доступное копирование по Enter только со стартовой страницы."""
        if self.stacked.currentWidget() is self.main_page:
            self.start_button.click()

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        logger.info("[%s] %s", timestamp, message)

    def start_the_backup(self):
        destination_root = self.state_manager.destination_path
        source_drives = self.state_manager.source_paths
        self.backup_controller.start_new_backup(
            destination_root=destination_root,
            source_drives=source_drives,
        )

    def open_settings(self):
        try:
            self.show_settings_page()
        except Exception as e:
            logger.error("Ошибка при открытии окна настроек: %s", e)
            import traceback
            traceback.print_exc()

    def show_main_page(self) -> None:
        self.stacked.setCurrentWidget(self.main_page)

    def show_settings_page(self) -> None:
        self.settings_page.refresh_from_app_state()
        self.stacked.setCurrentWidget(self.settings_page)

    def show_progress_page(self) -> None:
        """Переключение на страницу прогресса копирования (как у настроек)."""
        self.stacked.setCurrentWidget(self.progress_page)

    def reset_after_backup(self) -> None:
        """Очищает завершённую сессию и возвращает приложение на стартовый экран."""
        self._clear_all_fields()
        self._saved_geometry_before_transition = None
        self.start_transition_from_progress()

    def _setup_transition_animations(self) -> None:
        """Инициализация анимаций перехода (вызывается лениво при первом переходе)."""
        if self._transition_fade_animation is not None:
            return

        cw = self.centralWidget()
        self._transition_fade_effect = QGraphicsOpacityEffect(cw)
        cw.setGraphicsEffect(self._transition_fade_effect)
        self._transition_fade_effect.setOpacity(1.0)

        self._transition_fade_animation = QPropertyAnimation(
            self._transition_fade_effect, b"opacity", self
        )
        self._transition_fade_animation.setDuration(UIAnimation.TRANSITION_DURATION_MS // 2)
        self._transition_fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        if self._transition_resize_animation is None:
            self._transition_resize_animation = QPropertyAnimation(self, b"size", self)
            self._transition_resize_animation.setDuration(UIAnimation.TRANSITION_DURATION_MS)
            self._transition_resize_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def _release_transition_fade_effect(self) -> None:
        """Снять временный fade-эффект, чтобы не ломать эффекты дочерних виджетов."""
        animation = self._transition_fade_animation
        effect = self._transition_fade_effect
        if animation is not None:
            animation.stop()
            animation.setTargetObject(None)
            animation.deleteLater()
        if effect is not None and self.centralWidget().graphicsEffect() is effect:
            self.centralWidget().setGraphicsEffect(None)
        self._transition_fade_animation = None
        self._transition_fade_effect = None

    @staticmethod
    def _disconnect_all(signal) -> None:
        """Отключает текущие слоты сигнала без несовместимого QObject.receivers()."""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                signal.disconnect()
        except (TypeError, RuntimeError):
            pass

    def start_transition_to_progress(self) -> None:
        """Анимированный переход на progress_page (fade-out + resize + fade-in)."""
        if self._is_transitioning:
            return
        self._is_transitioning = True

        self._setup_transition_animations()

        self._saved_geometry_before_transition = self.frameGeometry()

        self._disconnect_all(self._transition_fade_animation.finished)
        self._transition_fade_animation.finished.connect(self._on_transition_to_progress_fade_out_done)
        self._transition_fade_animation.setStartValue(1.0)
        self._transition_fade_animation.setEndValue(0.0)
        self._transition_fade_animation.start()

    def _on_transition_to_progress_fade_out_done(self) -> None:
        """Fade-out завершён: переключить страницу, resize, fade-in."""
        try:
            self._transition_fade_animation.finished.disconnect(self._on_transition_to_progress_fade_out_done)
        except (TypeError, RuntimeError):
            pass

        self.stacked.setCurrentWidget(self.progress_page)

        target_height = UIAnimation.PROGRESS_PAGE_HEIGHT
        self.setMinimumHeight(target_height)

        self._disconnect_all(self._transition_resize_animation.finished)
        self._transition_resize_animation.finished.connect(self._on_transition_to_progress_resize_done)
        self._transition_resize_animation.setStartValue(self.size())
        self._transition_resize_animation.setEndValue(QSize(self.width(), target_height))
        self._transition_resize_animation.start()

    def _on_transition_to_progress_resize_done(self) -> None:
        """Resize завершён: fade-in."""
        try:
            self._transition_resize_animation.finished.disconnect(self._on_transition_to_progress_resize_done)
        except (TypeError, RuntimeError):
            pass

        self._disconnect_all(self._transition_fade_animation.finished)
        self._transition_fade_animation.finished.connect(self._on_transition_to_progress_fade_in_done)
        self._transition_fade_animation.setStartValue(0.0)
        self._transition_fade_animation.setEndValue(1.0)
        self._transition_fade_animation.start()

    def _on_transition_to_progress_fade_in_done(self) -> None:
        """Переход на progress завершён."""
        try:
            self._transition_fade_animation.finished.disconnect(self._on_transition_to_progress_fade_in_done)
        except (TypeError, RuntimeError):
            pass
        self._release_transition_fade_effect()
        self._is_transitioning = False

    def start_transition_from_progress(self) -> None:
        """Анимированный возврат на main_page (fade-out + resize + fade-in)."""
        if self._is_transitioning:
            return
        self._is_transitioning = True

        self._setup_transition_animations()

        self._disconnect_all(self._transition_fade_animation.finished)
        self._transition_fade_animation.finished.connect(self._on_transition_from_progress_fade_out_done)
        self._transition_fade_animation.setStartValue(1.0)
        self._transition_fade_animation.setEndValue(0.0)
        self._transition_fade_animation.start()

    def _on_transition_from_progress_fade_out_done(self) -> None:
        """Fade-out завершён: переключить страницу, resize, fade-in."""
        try:
            self._transition_fade_animation.finished.disconnect(self._on_transition_from_progress_fade_out_done)
        except (TypeError, RuntimeError):
            pass

        self.stacked.setCurrentWidget(self.main_page)

        if self._saved_geometry_before_transition is not None:
            target_height = self._saved_geometry_before_transition.height()
        else:
            target_height = self._content_height_for_cards(len(self._source_items))

        self._disconnect_all(self._transition_resize_animation.finished)
        self._transition_resize_animation.finished.connect(self._on_transition_from_progress_resize_done)
        self._transition_resize_animation.setStartValue(self.size())
        self._transition_resize_animation.setEndValue(QSize(self.width(), target_height))
        self._transition_resize_animation.start()

    def _on_transition_from_progress_resize_done(self) -> None:
        """Resize завершён: восстановить минимальный размер, fade-in."""
        try:
            self._transition_resize_animation.finished.disconnect(self._on_transition_from_progress_resize_done)
        except (TypeError, RuntimeError):
            pass

        self._update_window_min_height()

        self._disconnect_all(self._transition_fade_animation.finished)
        self._transition_fade_animation.finished.connect(self._on_transition_from_progress_fade_in_done)
        self._transition_fade_animation.setStartValue(0.0)
        self._transition_fade_animation.setEndValue(1.0)
        self._transition_fade_animation.start()

    def _on_transition_from_progress_fade_in_done(self) -> None:
        """Возврат на main завершён."""
        try:
            self._transition_fade_animation.finished.disconnect(self._on_transition_from_progress_fade_in_done)
        except (TypeError, RuntimeError):
            pass
        self._release_transition_fade_effect()
        self._is_transitioning = False
        self._saved_geometry_before_transition = None
