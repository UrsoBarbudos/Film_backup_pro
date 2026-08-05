"""
Окно/страница прогресса копирования приложения Dублёр (PySide6 версия).
Отвечает только за отображение UI и анимации.
Используется как страница в QStackedWidget (ProgressPage) с callback возврата на main.
"""

import os
import time
import math
import subprocess
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QMessageBox,
    QWidget,
    QSizePolicy,
)
from PySide6.QtCore import (
    Qt,
    Signal,
    QObject,
    QTimer,
    QElapsedTimer,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtGui import QFont, QShowEvent

from utils import format_size
from widgets import ElidedLabel
from progress_view_model import ProgressViewModel
from verification_dialog_handler import VerificationDialogHandler
from copy_conflict_dialog_handler import CopyConflictDialogHandler
from disk_ejector import eject_volume, external_volumes_for_sources
from ui.ui_constants import UISpacing, UISizes, UIAnimation
from backup_components.completion_status import BackupCompletionStatus


class ProgressSignals(QObject):
    """Класс-посредник для thread-safe обновления UI через Qt Signals"""
    progress_updated = Signal(float, float, float, float, str)  # процент, скопировано_МБ, всего_МБ, скорость, текущий_файл
    status_updated = Signal(str)  # текстовое сообщение статуса
    finished = Signal(str, str, object)  # completion_status, сообщение, статистика
    verification_error = Signal(str, str, str)  # source_path, destination_path, error_message - запрос действия пользователя
    copy_conflict = Signal(str, str, str)  # source_path, destination_path, filename - файл уже существует
    log_message = Signal(str)  # сообщение для лога процесса


class ProgressPage(QWidget):
    """Страница прогресса копирования (QWidget для встраивания в QStackedWidget)."""
    
    def __init__(
        self,
        parent: QWidget,
        app_instance: QWidget,
        on_close: Optional[Callable[[], None]] = None,
        view_model: Optional[ProgressViewModel] = None,
        dialog_handler: Optional[VerificationDialogHandler] = None,
    ):
        """
        :param parent: Родительский виджет (например QStackedWidget)
        :param app_instance: Экземпляр главного приложения для доступа к настройкам
        :param on_close: Callback возврата на главную страницу (вызывается при «Закрыть»/«Завершить»)
        :param view_model: ViewModel (опционально; при запуске копирования задаётся через prepare_for_run)
        :param dialog_handler: Handler диалогов проверки (опционально; задаётся через prepare_for_run)
        """
        super().__init__(parent)
        
        self.app = app_instance
        self.theme = getattr(app_instance, 'theme', 'light') or 'light'
        self.on_close = on_close
        
        self.view_model = view_model if view_model else ProgressViewModel()
        self.dialog_handler = dialog_handler if dialog_handler else VerificationDialogHandler()
        self.copy_conflict_dialog_handler = CopyConflictDialogHandler()
        
        # В режиме страницы внутри QStackedWidget ширина должна задаваться родителем.
        # Жёсткая минимальная ширина здесь приводила к клиппингу справа.
        self.setMinimumHeight(250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Создаем сигналы для thread-safe обновления (используются из фонового потока)
        self.signals = ProgressSignals()
        self.signals.progress_updated.connect(self._on_progress_updated)
        self.signals.status_updated.connect(self._on_status_updated)
        self.signals.finished.connect(self._on_finished)
        self.signals.verification_error.connect(self._on_verification_error)
        self.signals.copy_conflict.connect(self._on_copy_conflict)
        self.signals.log_message.connect(self._on_log_message)
        
        self._connect_view_model()
        
        # Таймеры для анимации (остаются здесь, так как это визуальная часть)
        self.verification_timer = QTimer()
        self.verification_timer.timeout.connect(self._update_verification_timer)
        self.verification_timer.setInterval(100)  # Обновление каждые 100мс для плавности
        
        self.pulse_animation_timer = QTimer()
        self.pulse_animation_timer.timeout.connect(self._update_pulse_animation)
        self.pulse_animation_timer.setInterval(50)  # Обновление каждые 50мс для более плавной анимации
        self.pulse_phase = 0.0
        
        # Таймер для автоматического закрытия окна при отмене
        self._auto_close_timer = None
        # Счетчик обратного отсчета для автоматического закрытия (в секундах)
        self._auto_close_countdown = 0
        
        # Двухшаговая отмена: первый клик — жёлтая кнопка с обратным отсчётом 6 сек, второй — отмена
        self._cancel_pending = False
        self._cancel_pending_timer: Optional[QTimer] = None
        self._cancel_pending_countdown = 0  # 6, 5, 4, 3, 2, 1 → 0 = сброс
        
        # Инициализируем путь назначения
        self.destination_path = ''
        self.source_paths: list[str] = []
        
        # Создаем интерфейс
        self._create_widgets()

        self._progress_animation = QPropertyAnimation(self.progress_bar, b"value", self)
        self._progress_animation.setDuration(UIAnimation.PROGRESS_DURATION_MS)
        self._progress_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._last_confirmed_progress_value = 0
        self._speed_update_clock = QElapsedTimer()
        self._eta_update_clock = QElapsedTimer()
        self._pending_speed_text: Optional[str] = None
        self._pending_eta_text: Optional[str] = None
        self._speed_update_timer = QTimer(self)
        self._speed_update_timer.setSingleShot(True)
        self._speed_update_timer.timeout.connect(self._flush_pending_speed_text)
        self._eta_update_timer = QTimer(self)
        self._eta_update_timer.setSingleShot(True)
        self._eta_update_timer.timeout.connect(self._flush_pending_eta_text)
        self._copy_activity_clock = QElapsedTimer()
        self._copy_activity_timer = QTimer(self)
        self._copy_activity_timer.setSingleShot(True)
        self._copy_activity_timer.timeout.connect(self._flush_pending_copy_activity)
        self._copy_activity_watch_timer = QTimer(self)
        self._copy_activity_watch_timer.setInterval(UIAnimation.COPY_ACTIVITY_WATCH_INTERVAL_MS)
        self._copy_activity_watch_timer.timeout.connect(self._check_copy_activity)
        self._pending_copy_activity_text: Optional[str] = None
        self._last_activity_copied_bytes: Optional[int] = None
        self._last_copy_growth_time: Optional[float] = None
        self._copy_activity_active = False
        self._copy_activity_finalized = False
        
        # Применяем тему
        self._apply_theme()
        
        # Устанавливаем начальный монохромный цвет прогресс-бара для этапа копирования
        initial_copy_color = '#D9D9D9' if self.theme == 'dark' else '#333333'
        self.set_progress_bar_color(initial_copy_color)

    def _connect_view_model(self) -> None:
        """Подключает сигналы текущего view_model к слотам UI (thread-safe)."""
        vm = self.view_model
        vm.progress_changed.connect(self._on_viewmodel_progress_changed, Qt.ConnectionType.QueuedConnection)
        vm.status_changed.connect(self._on_viewmodel_status_changed, Qt.ConnectionType.QueuedConnection)
        vm.paused_changed.connect(self._on_viewmodel_paused_changed, Qt.ConnectionType.QueuedConnection)
        vm.cancelled_changed.connect(self._on_viewmodel_cancelled_changed, Qt.ConnectionType.QueuedConnection)
        vm.verification_started.connect(self._on_viewmodel_verification_started, Qt.ConnectionType.QueuedConnection)
        vm.verification_stopped.connect(self._on_viewmodel_verification_stopped, Qt.ConnectionType.QueuedConnection)
    
    def _disconnect_view_model(self) -> None:
        """Отключает сигналы текущего view_model от слотов."""
        try:
            self.view_model.progress_changed.disconnect(self._on_viewmodel_progress_changed)
            self.view_model.status_changed.disconnect(self._on_viewmodel_status_changed)
            self.view_model.paused_changed.disconnect(self._on_viewmodel_paused_changed)
            self.view_model.cancelled_changed.disconnect(self._on_viewmodel_cancelled_changed)
            self.view_model.verification_started.disconnect(self._on_viewmodel_verification_started)
            self.view_model.verification_stopped.disconnect(self._on_viewmodel_verification_stopped)
        except TypeError:
            pass
    
    def prepare_for_run(
        self,
        view_model: ProgressViewModel,
        dialog_handler: VerificationDialogHandler,
        source_paths: Optional[list[str]] = None,
    ) -> None:
        """Подготовка страницы к новому запуску копирования: подмена ViewModel и handler, сброс UI."""
        self._disconnect_view_model()
        self.view_model = view_model
        self.dialog_handler = dialog_handler
        self.source_paths = list(source_paths or [])
        self._connect_view_model()
        self._reset_ui_state()
    
    def _reset_ui_state(self) -> None:
        """Сброс визуального состояния перед новым запуском."""
        self._reset_progress_display()
        self.pause_button.show()
        self.pause_button.setEnabled(True)
        self.pause_button.setText("Пауза")
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Отмена")
        self.cancel_button.setStyleSheet("")
        self.finish_button.hide()
        self.open_folder_button.hide()
        self.eject_button.hide()
        self._refresh_action_buttons_layout()
        self.clear_cancel_pending()
        self.current_file_container.show()
        self.stats_container.show()
        # Скорость уже входит в живую строку «Скопировано … · … МБ/с».
        self.speed_label.hide()
        self.time_label.show()
        self.remaining_label.show()
        self.verification_time_label.show()
        self.current_file_title.setText("Копирование:")
        self.current_file_label.setText("Ожидание...")
        self.speed_label.setText("Скорость: -- МБ/с")
        self.copied_label.setText("Скопировано: -- из --")
        self.remaining_label.setText("Осталось: --")
        self.time_label.setText("Осталось времени: --")
        self.completion_container.hide()
        if self._auto_close_timer is not None:
            self._auto_close_timer.stop()
            self._auto_close_timer = None
        self._auto_close_countdown = 0
        self.destination_path = ''
    
    def _request_back(self) -> None:
        """Возврат на главную страницу; при активном копировании — запрос подтверждения."""
        copy_completed = self.finish_button.isVisible()
        if not copy_completed and not self.view_model.is_cancelled and self.pause_button.isEnabled():
            reply = QMessageBox.question(
                self,
                "Подтверждение закрытия",
                "Копирование ещё не завершено. Вы уверены, что хотите закрыть?\n\nПримечание: процесс копирования продолжится в фоне.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if self.on_close:
            self.on_close()
    
    @property
    def is_paused(self) -> bool:
        """Возвращает состояние паузы из ViewModel"""
        return self.view_model.is_paused
    
    @property
    def is_cancelled(self) -> bool:
        """Возвращает состояние отмены из ViewModel"""
        return self.view_model.is_cancelled
    
    def is_cancel_pending(self) -> bool:
        """Возвращает True, если кнопка в состоянии «подтвердить отмену» (жёлтая)."""
        return self._cancel_pending
    
    def set_cancel_pending(self, pending: bool) -> None:
        """Включает состояние «ожидание отмены»: жёлтая кнопка «Отмена (6)», обратный отсчёт 6 сек."""
        if not pending:
            self.clear_cancel_pending()
            return
        self._cancel_pending = True
        self._cancel_pending_countdown = 10
        self.cancel_button.setStyleSheet("background-color: #f0ad4e; color: #000")
        self.cancel_button.setText("Отмена (10)")
        if self._cancel_pending_timer is not None:
            self._cancel_pending_timer.stop()
        self._cancel_pending_timer = QTimer()
        self._cancel_pending_timer.timeout.connect(self._on_cancel_pending_tick)
        self._cancel_pending_timer.start(1000)  # каждую секунду
    
    def clear_cancel_pending(self) -> None:
        """Сбрасывает состояние «ожидание отмены»: обычная кнопка «Отмена»."""
        self._cancel_pending = False
        self._cancel_pending_countdown = 0
        if self._cancel_pending_timer is not None:
            self._cancel_pending_timer.stop()
            self._cancel_pending_timer = None
        self.cancel_button.setStyleSheet("")
        self.cancel_button.setText("Отмена")
    
    def _on_cancel_pending_tick(self) -> None:
        """Каждую секунду: уменьшаем счётчик, обновляем текст; при 0 — сброс без отмены."""
        self._cancel_pending_countdown -= 1
        if self._cancel_pending_countdown <= 0:
            self.clear_cancel_pending()
            return
        self.cancel_button.setText(f"Отмена ({self._cancel_pending_countdown})")
    
    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        if self.isWindow():
            self._center_window()
    
    def _center_window(self) -> None:
        """Центрирует окно на экране (только при использовании как отдельное окно)."""
        if self.parent():
            parent_geometry = self.parent().frameGeometry()
            parent_center = parent_geometry.center()
            self.move(parent_center.x() - self.width() // 2,
                     parent_center.y() - self.height() // 2)

    def _create_widgets(self):
        """Создает все виджеты окна прогресса"""
        
        # Геометрия:
        # - внешний layout без горизонтальных inset
        # - контент и нижние кнопки в одной ширине (без боковых inset),
        #   чтобы прогресс-бар и текстовые блоки были выровнены по кнопкам.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 16, 0, 0)
        main_layout.setSpacing(0)

        content_container = QWidget(self)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Заголовок
        self.title_label = QLabel("Прогресс")
        title_font = QFont("Arial", 18, QFont.Weight.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.title_label)
        content_layout.addSpacing(10)
        
        # Прогресс-бар
        progress_layout = QVBoxLayout()
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(4)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(UIAnimation.PROGRESS_SCALE)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.progress_bar)
        self.progress_percent_label = QLabel("0%")
        self.progress_percent_label.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        self.progress_percent_label.setObjectName("ProgressPercentLabel")
        self.progress_percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.progress_percent_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        progress_layout.addWidget(self.progress_percent_label)
        content_layout.addLayout(progress_layout)
        content_layout.addSpacing(16)  # зазор прогресс-бар -> Текущий файл
        
        # Контейнер для секции "Текущий файл" (для возможности скрытия при завершении)
        self.current_file_container = QWidget()
        current_file_container_layout = QVBoxLayout(self.current_file_container)
        current_file_container_layout.setContentsMargins(0, 0, 0, 0)
        current_file_container_layout.setSpacing(0)
        
        # Текущий файл (метка и имя в одну строку)
        current_file_row = QHBoxLayout()
        current_file_row.setContentsMargins(0, 0, 0, 0)
        current_file_row.setSpacing(6)
        self.current_file_title = QLabel("Копирование:")
        self.current_file_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.current_file_title.setObjectName("CurrentFileTitle")
        current_file_row.addWidget(self.current_file_title)
        self.current_file_label = ElidedLabel("Ожидание...")
        self.current_file_label.setFont(QFont("Arial", 10))
        self.current_file_label.setObjectName("CurrentFileLabel")
        self.current_file_label.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        current_file_row.addWidget(self.current_file_label, 1)  # stretch=1 чтобы имя занимало оставшееся место и эллипсис работал
        current_file_container_layout.addLayout(current_file_row)
        
        content_layout.addWidget(self.current_file_container)
        content_layout.addSpacing(8)  # зазор Текущий файл -> статистика
        
        # Контейнер статистики (видим во время копирования)
        self.stats_container = QWidget()
        stats_layout = QVBoxLayout(self.stats_container)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(4)
        self.speed_label = QLabel("Скорость: -- МБ/с")
        self.speed_label.setFont(QFont("Arial", 10))
        self.speed_label.setObjectName("StatsLabel")
        stats_layout.addWidget(self.speed_label)
        self.speed_label.hide()
        self.copied_label = QLabel("Скопировано: -- из --")
        self.copied_label.setFont(QFont("Arial", 10))
        self.copied_label.setObjectName("StatsLabel")
        stats_layout.addWidget(self.copied_label)
        self.remaining_label = QLabel("Осталось: --")
        self.remaining_label.setFont(QFont("Arial", 10))
        self.remaining_label.setObjectName("StatsLabel")
        stats_layout.addWidget(self.remaining_label)
        self.time_label = QLabel("Осталось времени: --")
        self.time_label.setFont(QFont("Arial", 10))
        self.time_label.setObjectName("StatsLabel")
        stats_layout.addWidget(self.time_label)
        self.verification_time_label = QLabel("")
        self.verification_time_label.setFont(QFont("Arial", 10))
        self.verification_time_label.setObjectName("StatsLabel")
        stats_layout.addWidget(self.verification_time_label)
        content_layout.addWidget(self.stats_container)
        
        # Контейнер деталей завершения (скрыт по умолчанию, заменяет статистику по завершении)
        self.completion_container = QWidget()
        completion_layout = QVBoxLayout(self.completion_container)
        completion_layout.setContentsMargins(0, 0, 0, 0)
        completion_layout.setSpacing(8)
        self.completion_title_widget = QLabel("Итог:")
        self.completion_title_widget.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.completion_title_widget.setObjectName("CompletionTitle")
        completion_layout.addWidget(self.completion_title_widget)
        self.completion_status_label = QLabel("")
        self.completion_status_label.setFont(QFont("Arial", 11))
        self.completion_status_label.setObjectName("CompletionStatusLabel")
        completion_layout.addWidget(self.completion_status_label)
        self.completion_stats_label = QLabel("")
        self.completion_stats_label.setFont(QFont("Arial", 10))
        self.completion_stats_label.setObjectName("CompletionStatsLabel")
        completion_layout.addWidget(self.completion_stats_label)
        self.completion_time_label = QLabel("")
        self.completion_time_label.setFont(QFont("Arial", 10))
        self.completion_time_label.setObjectName("CompletionTimeLabel")
        completion_layout.addWidget(self.completion_time_label)
        self.completion_volume_label = QLabel("")
        self.completion_volume_label.setFont(QFont("Arial", 10))
        self.completion_volume_label.setObjectName("CompletionVolumeLabel")
        completion_layout.addWidget(self.completion_volume_label)
        self.completion_speed_label = QLabel("")
        self.completion_speed_label.setFont(QFont("Arial", 10))
        self.completion_speed_label.setObjectName("CompletionSpeedLabel")
        completion_layout.addWidget(self.completion_speed_label)
        self.completion_project_label = QLabel("")
        self.completion_project_label.setFont(QFont("Arial", 10))
        self.completion_project_label.setObjectName("CompletionStatsLabel")
        completion_layout.addWidget(self.completion_project_label)
        self.completion_destination_label = ElidedLabel("")
        self.completion_destination_label.setFont(QFont("Arial", 10))
        self.completion_destination_label.setObjectName("CompletionStatsLabel")
        self.completion_destination_label.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        completion_layout.addWidget(self.completion_destination_label)
        self.completion_sources_label = QLabel("")
        self.completion_sources_label.setFont(QFont("Arial", 10))
        self.completion_sources_label.setObjectName("CompletionStatsLabel")
        completion_layout.addWidget(self.completion_sources_label)
        self.completion_categories_label = QLabel("")
        self.completion_categories_label.setFont(QFont("Arial", 10))
        self.completion_categories_label.setObjectName("CompletionStatsLabel")
        completion_layout.addWidget(self.completion_categories_label)
        self.completion_container.hide()
        self.completion_title_widget.hide()
        self.completion_status_label.hide()
        self.completion_stats_label.hide()
        self.completion_time_label.hide()
        self.completion_volume_label.hide()
        self.completion_speed_label.hide()
        self.completion_project_label.hide()
        self.completion_destination_label.hide()
        self.completion_sources_label.hide()
        self.completion_categories_label.hide()
        content_layout.addWidget(self.completion_container)
        
        content_layout.addSpacing(12)
        content_layout.addStretch(1)  # забирает лишнюю высоту окна, чтобы блоки контента не растягивались
        main_layout.addWidget(content_container)
        # Кнопки управления (внизу окна)
        buttons_layout = QHBoxLayout()
        # Горизонтальные inset не добавляем: ширина ряда должна совпадать
        # с рядом кнопки в главном окне (новый UI).
        buttons_layout.setContentsMargins(0, UISpacing.BUTTONS, 0, 0)
        buttons_layout.setSpacing(UISpacing.INTERNAL)
        self.buttons_layout = buttons_layout
        
        self.pause_button = QPushButton("Пауза")
        self.pause_button.setFixedHeight(UISizes.BUTTON_HEIGHT)
        self.pause_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setFixedHeight(UISizes.BUTTON_HEIGHT)
        self.cancel_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        
        self.open_folder_button = QPushButton("Открыть папку")
        self.open_folder_button.setFixedHeight(UISizes.BUTTON_HEIGHT)
        self.open_folder_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.open_folder_button.clicked.connect(self._on_open_folder_clicked)
        self.open_folder_button.hide()

        self.eject_button = QPushButton("Извлечь и завершить")
        self.eject_button.setFixedHeight(UISizes.BUTTON_HEIGHT)
        self.eject_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.eject_button.clicked.connect(self._on_eject_clicked)
        self.eject_button.hide()
        
        self.finish_button = QPushButton("Завершить")
        self.finish_button.setFixedHeight(UISizes.BUTTON_HEIGHT)
        self.finish_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.finish_button.setObjectName("FinishButton")
        self.finish_button.clicked.connect(self._on_finish_clicked)
        self.finish_button.hide()
        self._action_buttons = [
            self.pause_button,
            self.cancel_button,
            self.open_folder_button,
            self.eject_button,
            self.finish_button,
        ]
        self._refresh_action_buttons_layout()
        
        main_layout.addLayout(buttons_layout)

    def _refresh_action_buttons_layout(self) -> None:
        """
        Пересобирает ряд action-кнопок только из видимых элементов.
        Это предотвращает «уезд» вправо, когда часть кнопок скрыта.
        """
        if not hasattr(self, "buttons_layout") or not hasattr(self, "_action_buttons"):
            return

        for button in self._action_buttons:
            self.buttons_layout.removeWidget(button)

        visible_buttons = [button for button in self._action_buttons if button.isVisible()]
        for button in visible_buttons:
            self.buttons_layout.addWidget(button, 1)
    
    def _apply_theme(self):
        """Применяет тему оформления к окну прогресса"""
        if self.theme == 'dark':
            self.setStyleSheet("""
                QDialog {
                    background-color: #2b2b2b;
                    color: #FAFAFA;
                }
                QWidget {
                    background-color: #2b2b2b;
                    color: #FAFAFA;
                }
                QLabel#TitleLabel {
                    color: #FAFAFA;
                    font-weight: bold;
                }
                QLabel#StatsLabel {
                    color: #aaa;
                }
                QLabel#CurrentFileTitle {
                    color: #FAFAFA;
                }
                QLabel#CurrentFileLabel {
                    color: #aaa;
                }
                QLabel#CompletionTitle {
                    color: #FAFAFA;
                    font-weight: bold;
                }
                QLabel#CompletionStatusLabel {
                    color: #2FA572;
                    font-weight: bold;
                }
                QLabel#CompletionStatsLabel {
                    color: #aaa;
                }
                QLabel#CompletionTimeLabel {
                    color: #aaa;
                }
                QLabel#CompletionVolumeLabel {
                    color: #aaa;
                }
                QLabel#CompletionSpeedLabel {
                    color: #aaa;
                }
                QLabel#ProgressPercentLabel {
                    color: #FAFAFA;
                    padding-right: 0px;
                    padding-top: 4px;
                }
                QProgressBar {
                    background-color: #2b2b2b;
                    border: 2px solid #FAFAFA;
                    border-radius: 0px;
                    text-align: center;
                    color: #FAFAFA;
                    height: 28px;
                }
                QProgressBar::chunk {
                    background-color: #D9D9D9;
                    border-radius: 0px;
                }
                QPushButton {
                    background-color: #555;
                    color: #FAFAFA;
                    border: none;
                    border-radius: 4px;
                    padding: 8px;
                }
                QPushButton:hover {
                    background-color: #666;
                }
                QPushButton:pressed {
                    background-color: #444;
                }
                QPushButton#FinishButton {
                    background-color: #2FA572;
                    color: #FAFAFA;
                    border: none;
                    border-radius: 4px;
                    padding: 8px;
                }
                QPushButton#FinishButton:hover {
                    background-color: #28A066;
                }
                QPushButton#FinishButton:pressed {
                    background-color: #22995A;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #FAFAFA;
                    color: black;
                }
                QWidget {
                    background-color: #FAFAFA;
                    color: black;
                }
                QLabel#TitleLabel {
                    color: black;
                    font-weight: bold;
                }
                QLabel#StatsLabel {
                    color: #666;
                }
                QLabel#CurrentFileTitle {
                    color: black;
                }
                QLabel#CurrentFileLabel {
                    color: #666;
                }
                QLabel#CompletionTitle {
                    color: black;
                    font-weight: bold;
                }
                QLabel#CompletionStatusLabel {
                    color: #2FA572;
                    font-weight: bold;
                }
                QLabel#CompletionStatsLabel {
                    color: #666;
                }
                QLabel#CompletionTimeLabel {
                    color: #666;
                }
                QLabel#CompletionVolumeLabel {
                    color: #666;
                }
                QLabel#CompletionSpeedLabel {
                    color: #666;
                }
                QLabel#ProgressPercentLabel {
                    color: #111111;
                    padding-right: 0px;
                    padding-top: 4px;
                }
                QProgressBar {
                    background-color: #FAFAFA;
                    border: 2px solid #111111;
                    border-radius: 0px;
                    text-align: center;
                    color: black;
                    height: 28px;
                }
                QProgressBar::chunk {
                    background-color: #333333;
                    border-radius: 0px;
                }
                QPushButton {
                    background-color: #999;
                    color: #FAFAFA;
                    border: none;
                    border-radius: 4px;
                    padding: 8px;
                }
                QPushButton:hover {
                    background-color: #888;
                }
                QPushButton:pressed {
                    background-color: #777;
                }
                QPushButton#FinishButton {
                    background-color: #2FA572;
                    color: #FAFAFA;
                    border: none;
                    border-radius: 4px;
                    padding: 8px;
                }
                QPushButton#FinishButton:hover {
                    background-color: #26B068;
                }
                QPushButton#FinishButton:pressed {
                    background-color: #1F9A5A;
                }
            """)
    
    def set_progress_bar_color(self, color: str, animated: bool = False):
        """
        Динамически изменяет цвет заполнения прогресс-бара
        
        :param color: Цвет в формате hex (например, '#2FA572')
        :param animated: Если True, добавляет анимацию пульсации
        """
        # Получаем базовые стили для прогресс-бара в зависимости от темы
        if self.theme == 'dark':
            base_style = """
                QProgressBar {
                    background-color: #2b2b2b;
                    border: 2px solid #FAFAFA;
                    border-radius: 0px;
                    text-align: center;
                    color: #FAFAFA;
                    height: 28px;
                }
            """
        else:
            base_style = """
                QProgressBar {
                    background-color: #FAFAFA;
                    border: 2px solid #111111;
                    border-radius: 0px;
                    text-align: center;
                    color: black;
                    height: 28px;
                }
            """
        
        # Добавляем стиль для chunk с указанным цветом
        if animated:
            # Для Qt анимация управляется через QTimer (_update_pulse_animation),
            # здесь задаём базовый цвет чанка.
            chunk_style = f"""
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 0px;
                }}
            """
        else:
            chunk_style = f"""
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 0px;
                }}
            """
        
        # Применяем комбинированные стили к прогресс-бару
        self.progress_bar.setStyleSheet(base_style + chunk_style)
    
    def _on_viewmodel_progress_changed(self, percent: float, copied_mb: float, total_mb: float, speed_mbps: float, current_file: str):
        """
        Обновляет UI при изменении прогресса в ViewModel
        
        :param percent: Процент выполнения (0-100)
        :param copied_mb: Скопировано МБ
        :param total_mb: Всего МБ
        :param speed_mbps: Скорость в МБ/с
        :param current_file: Путь к текущему файлу
        """
        # Пропускаем обновление UI если данные невалидны
        # UI уже обновлен напрямую из _on_progress_updated через _update_ui_directly_from_mb
        if total_mb <= 0 or copied_mb < 0:
            return
        
        # Обновляем UI используя значения в МБ напрямую (избегаем переполнения)
        # Метод _update_ui_directly_from_mb обновляет весь UI полностью
        self._update_ui_directly_from_mb(percent, copied_mb, total_mb, speed_mbps, current_file)
    
    def _update_verification_timer(self):
        """Обновляет отображение оставшегося времени проверки"""
        # Проверяем, есть ли информация о прогрессе проверки
        total_start_time = self.view_model.verification_total_start_time
        current_file_index = self.view_model.verification_current_file_index
        total_files = self.view_model.verification_total_files
        
        if total_start_time is not None and total_files > 0 and current_file_index > 0:
            # Вычисляем оставшееся время
            elapsed_total = time.time() - total_start_time
            files_processed = current_file_index - 1  # Уже обработано файлов (текущий еще обрабатывается)
            
            if files_processed > 0:
                # Среднее время на файл
                avg_time_per_file = elapsed_total / files_processed
                # Оставшиеся файлы
                remaining_files = total_files - current_file_index + 1  # +1 потому что текущий еще обрабатывается
                # Оставшееся время
                remaining_time = avg_time_per_file * remaining_files
                
                # Форматируем оставшееся время
                if remaining_time < 60:
                    display_text = f"Осталось: {int(remaining_time)} сек"
                    self.verification_time_label.setText(display_text)
                else:
                    minutes = int(remaining_time // 60)
                    seconds = int(remaining_time % 60)
                    display_text = f"Осталось: {minutes} мин {seconds} сек"
                    self.verification_time_label.setText(display_text)
            else:
                # Если еще нет обработанных файлов, показываем прошедшее время
                elapsed = time.time() - total_start_time
                if elapsed < 60:
                    self.verification_time_label.setText(f"Проверка файла: {int(elapsed)} сек")
                else:
                    minutes = int(elapsed // 60)
                    seconds = int(elapsed % 60)
                    self.verification_time_label.setText(f"Проверка файла: {minutes} мин {seconds} сек")
        elif self.view_model.verification_start_time is not None:
            # Fallback: если нет информации о прогрессе, показываем прошедшее время текущего файла
            elapsed = time.time() - self.view_model.verification_start_time
            if elapsed < 60:
                self.verification_time_label.setText(f"Проверка файла: {int(elapsed)} сек")
            else:
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                self.verification_time_label.setText(f"Проверка файла: {minutes} мин {seconds} сек")
    
    def _update_pulse_animation(self):
        """Обновляет анимацию пульсации прогресс-бара"""
        if not self.view_model.is_verifying:
            return
        
        # Увеличиваем фазу анимации медленнее для более плавной анимации
        self.pulse_phase += 0.02
        if self.pulse_phase >= 1.0:
            self.pulse_phase = 0.0
        
        pulse = 0.5 + 0.5 * math.sin(self.pulse_phase * 2 * math.pi)
        if self.theme == 'dark':
            brightness = int(170 + 85 * pulse)  # 170..255
        else:
            brightness = int(30 + 60 * pulse)  # 30..90
        
        # Получаем базовые стили
        if self.theme == 'dark':
            base_style = """
                QProgressBar {
                    background-color: #2b2b2b;
                    border: 2px solid #FAFAFA;
                    border-radius: 0px;
                    text-align: center;
                    color: #FAFAFA;
                    height: 28px;
                }
            """
        else:
            base_style = """
                QProgressBar {
                    background-color: #FAFAFA;
                    border: 2px solid #111111;
                    border-radius: 0px;
                    text-align: center;
                    color: black;
                    height: 28px;
                }
            """
        
        # Пульсация в оттенках серого для этапа проверки.
        chunk_style = f"""
            QProgressBar::chunk {{
                background-color: rgb({brightness}, {brightness}, {brightness});
                border-radius: 0px;
            }}
        """
        
        self.progress_bar.setStyleSheet(base_style + chunk_style)
    
    def _on_viewmodel_status_changed(self, message: str):
        """
        Обновляет UI при изменении статуса в ViewModel
        
        :param message: Текстовое сообщение статуса
        """
        status_type = self.view_model.status_type
        self._speed_update_clock.invalidate()
        self._eta_update_clock.invalidate()
        if status_type != "copying":
            self._stop_copy_activity(finalized=False)
        
        # Обновляем заголовок окна и заголовок внутри окна
        self.setWindowTitle(f"Прогресс копирования - {message}")
        
        # Заголовок над баром по референсу всегда одинаковый.
        self.title_label.setText("Прогресс")

        # Обновляем UI в зависимости от типа статуса
        if status_type == "scanning":
            self.current_file_title.setText("Сканирование:")
            # Останавливаем таймеры проверки
            self.verification_timer.stop()
            self.pulse_animation_timer.stop()
            self.verification_time_label.setText("")
        elif status_type == "verification":
            self.current_file_title.setText("Проверка:")
            # Монохромный стиль для этапа проверки с пульсацией.
            self.pulse_phase = 0.0
            verification_color = '#FFFFFF' if self.theme == 'dark' else '#111111'
            self.set_progress_bar_color(verification_color, animated=True)
            # Запускаем таймеры для нового файла
            if not self.verification_timer.isActive():
                self.verification_timer.start()
            if not self.pulse_animation_timer.isActive():
                self.pulse_animation_timer.start()
        elif status_type == "copying":
            self.current_file_title.setText("Копирование:")
            # Монохромный стиль для этапа копирования.
            # Останавливаем таймеры проверки
            self.verification_timer.stop()
            self.pulse_animation_timer.stop()
            self.verification_time_label.setText("")
            copying_color = '#D9D9D9' if self.theme == 'dark' else '#333333'
            self.set_progress_bar_color(copying_color, animated=False)

    def _set_percent_label_value(self, percent: int) -> None:
        """Обновляет отображение процента у правого угла прогресс-бара."""
        safe_percent = max(0, min(100, int(percent)))
        self.progress_percent_label.setText(f"{safe_percent}%")

    def _set_progress_target(self, percent: float, *, completed: bool = False) -> None:
        """Плавно двигает бар только к уже подтверждённому монотонному значению."""
        incoming_value = round(max(0.0, min(100.0, float(percent))) * 100)
        maximum = UIAnimation.PROGRESS_SCALE if completed else UIAnimation.PROGRESS_SCALE - 1
        target_value = min(maximum, max(self._last_confirmed_progress_value, incoming_value))
        self._last_confirmed_progress_value = target_value
        current_value = self.progress_bar.value()
        self._progress_animation.stop()
        if target_value <= current_value or self.view_model.is_paused:
            return
        self._progress_animation.setStartValue(current_value)
        self._progress_animation.setEndValue(target_value)
        self._progress_animation.start()

    def _update_throttled_text(self, *, text: str, label: QLabel, clock: QElapsedTimer,
                               timer: QTimer, interval_ms: int,
                               pending_attribute: str, force: bool = False) -> None:
        if force or not clock.isValid() or clock.elapsed() >= interval_ms:
            timer.stop()
            setattr(self, pending_attribute, None)
            label.setText(text)
            clock.restart()
            return
        setattr(self, pending_attribute, text)
        if not timer.isActive():
            timer.start(max(1, interval_ms - clock.elapsed()))

    def _update_speed_if_due(self, text: str, *, force: bool = False) -> None:
        self._update_throttled_text(
            text=text, label=self.speed_label, clock=self._speed_update_clock,
            timer=self._speed_update_timer, interval_ms=UIAnimation.SPEED_UPDATE_INTERVAL_MS,
            pending_attribute="_pending_speed_text", force=force,
        )

    def _update_eta_if_due(self, text: str, *, force: bool = False) -> None:
        self._update_throttled_text(
            text=text, label=self.time_label, clock=self._eta_update_clock,
            timer=self._eta_update_timer, interval_ms=UIAnimation.ETA_UPDATE_INTERVAL_MS,
            pending_attribute="_pending_eta_text", force=force,
        )

    def _flush_pending_speed_text(self) -> None:
        if self._pending_speed_text is not None:
            self._update_speed_if_due(self._pending_speed_text, force=True)

    def _flush_pending_eta_text(self) -> None:
        if self._pending_eta_text is not None:
            self._update_eta_if_due(self._pending_eta_text, force=True)

    @staticmethod
    def _format_copy_activity(copied_bytes: int, total_bytes: int, speed_mbps: float) -> str:
        copied_text = format_size(copied_bytes)
        speed_text = f"{speed_mbps:.2f} МБ/с" if speed_mbps > 0 else "-- МБ/с"
        if total_bytes > 0:
            return f"Скопировано {copied_text} из {format_size(total_bytes)} · {speed_text}"
        return f"Скопировано {copied_text} · {speed_text}"

    @staticmethod
    def _set_label_text_if_changed(label: QLabel, text: str) -> None:
        if label.text() != text:
            label.setText(text)

    def _update_copy_activity_text(self, text: str, *, force: bool = False) -> None:
        if self._copy_activity_finalized or self.view_model.is_paused:
            return
        if force or not self._copy_activity_clock.isValid() or (
            self._copy_activity_clock.elapsed() >= UIAnimation.COPY_ACTIVITY_UPDATE_INTERVAL_MS
        ):
            self._copy_activity_timer.stop()
            self._pending_copy_activity_text = None
            self._set_label_text_if_changed(self.copied_label, text)
            self._copy_activity_clock.restart()
            return
        self._pending_copy_activity_text = text
        if not self._copy_activity_timer.isActive():
            remaining = UIAnimation.COPY_ACTIVITY_UPDATE_INTERVAL_MS - self._copy_activity_clock.elapsed()
            self._copy_activity_timer.start(max(1, remaining))

    def _flush_pending_copy_activity(self) -> None:
        if self._pending_copy_activity_text is not None:
            self._update_copy_activity_text(self._pending_copy_activity_text, force=True)

    def _update_copy_activity(
        self, copied_bytes: int, total_bytes: int, speed_mbps: float
    ) -> None:
        if self.view_model.status_type != "copying" or self.view_model.is_paused:
            return
        self._copy_activity_active = True
        self._copy_activity_finalized = False
        if not self._copy_activity_watch_timer.isActive():
            self._copy_activity_watch_timer.start()

        grew = (
            self._last_activity_copied_bytes is None
            or copied_bytes > self._last_activity_copied_bytes
        )
        was_waiting = self.copied_label.text() == "Ожидание данных…"
        if grew:
            self._last_copy_growth_time = time.monotonic()
        self._last_activity_copied_bytes = max(
            copied_bytes, self._last_activity_copied_bytes or 0
        )
        text = self._format_copy_activity(copied_bytes, total_bytes, speed_mbps)
        self._update_copy_activity_text(text, force=was_waiting)

    def _check_copy_activity(self) -> None:
        if (
            not self._copy_activity_active
            or self._copy_activity_finalized
            or self.view_model.is_paused
            or self.view_model.status_type != "copying"
            or self._last_copy_growth_time is None
        ):
            return
        idle_ms = (time.monotonic() - self._last_copy_growth_time) * 1000
        if idle_ms >= UIAnimation.COPY_ACTIVITY_IDLE_TIMEOUT_MS:
            self._copy_activity_timer.stop()
            self._pending_copy_activity_text = None
            self._set_label_text_if_changed(self.copied_label, "Ожидание данных…")

    def _stop_copy_activity(self, *, finalized: bool) -> None:
        self._copy_activity_active = False
        self._copy_activity_finalized = finalized
        self._copy_activity_timer.stop()
        self._copy_activity_watch_timer.stop()
        self._pending_copy_activity_text = None

    def _reset_progress_display(self) -> None:
        """Останавливает анимацию и сбрасывает UI-state прогресса."""
        self._progress_animation.stop()
        self._speed_update_timer.stop()
        self._eta_update_timer.stop()
        self._stop_copy_activity(finalized=False)
        self._last_confirmed_progress_value = 0
        self._pending_speed_text = None
        self._pending_eta_text = None
        self._speed_update_clock.invalidate()
        self._eta_update_clock.invalidate()
        self._copy_activity_clock.invalidate()
        self._last_activity_copied_bytes = None
        self._last_copy_growth_time = None
        self.progress_bar.setValue(0)
        self._set_percent_label_value(0)
    
    def _on_viewmodel_paused_changed(self, paused: bool):
        """
        Обновляет UI при изменении состояния паузы в ViewModel
        
        :param paused: True если на паузе, False если работает
        """
        if paused:
            self._progress_animation.stop()
            self._speed_update_timer.stop()
            self._eta_update_timer.stop()
            self._pending_speed_text = None
            self._pending_eta_text = None
            self._stop_copy_activity(finalized=False)
            self._update_speed_if_due("Скорость: -- МБ/с", force=True)
            self._update_eta_if_due("Осталось времени: Пауза", force=True)
            self.pause_button.setText("Возобновить")
        else:
            self._speed_update_clock.invalidate()
            self._eta_update_clock.invalidate()
            self._last_copy_growth_time = time.monotonic()
            self.pause_button.setText("Пауза")
    
    def _on_viewmodel_cancelled_changed(self, cancelled: bool):
        """
        Обновляет UI при изменении состояния отмены в ViewModel
        
        :param cancelled: True если отменено, False если работает
        """
        if cancelled:
            self._progress_animation.stop()
            self._speed_update_timer.stop()
            self._eta_update_timer.stop()
            self._pending_speed_text = None
            self._pending_eta_text = None
            self._stop_copy_activity(finalized=True)
            self.cancel_button.setEnabled(False)
            self.pause_button.setEnabled(False)
    
    def _on_viewmodel_verification_started(self):
        """Обработчик начала проверки файла"""
        # Таймеры уже запускаются в _on_viewmodel_status_changed
        pass
    
    def _on_viewmodel_verification_stopped(self):
        """Обработчик окончания проверки файла"""
        self.verification_timer.stop()
        self.pulse_animation_timer.stop()
        self.verification_time_label.setText("")
    
    def set_paused(self, paused: bool):
        """
        Устанавливает состояние паузы в ViewModel
        
        :param paused: True если на паузе, False если работает
        """
        self.view_model.set_paused(paused)
    
    def _on_progress_updated(self, percent: float, copied_mb: float, total_mb: float, speed_mbps: float, current_file: str):
        """Передаёт входной снимок в ViewModel; виджеты здесь не меняются."""
        # Конвертируем обратно в байты для ViewModel (с защитой от переполнения)
        # Используем более безопасную конвертацию
        try:
            # Используем промежуточные переменные для избежания переполнения
            copied_bytes_safe = int(round(copied_mb)) * 1024 * 1024
            total_bytes_safe = int(round(total_mb)) * 1024 * 1024
            
            # Проверяем на переполнение (если значение слишком большое для int32)
            if copied_bytes_safe < 0 or total_bytes_safe < 0 or copied_bytes_safe > 2147483647 or total_bytes_safe > 2147483647:
                # Используем альтернативный метод: умножаем по частям
                copied_bytes = int(copied_mb * 1048576.0)  # 1024*1024 как float
                total_bytes = int(total_mb * 1048576.0)
            else:
                copied_bytes = copied_bytes_safe
                total_bytes = total_bytes_safe
        except (OverflowError, ValueError):
            # Если все еще переполнение, используем значения из сигнала напрямую
            # Конвертируем только если значения не слишком большие
            if total_mb < 2147483.647:  # Примерно 2TB в МБ
                copied_bytes = int(copied_mb * 1048576.0)
                total_bytes = int(total_mb * 1048576.0)
            else:
                # Для очень больших значений используем 0, чтобы не сломать UI
                copied_bytes = 0
                total_bytes = 0
        
        # Обновляем ViewModel для сохранения состояния (если значения валидны)
        if total_bytes >= 0 and copied_bytes >= 0:
            self.view_model.update_progress(percent, copied_bytes, total_bytes, speed_mbps, current_file)
    
    def _update_ui_directly_from_mb(self, percent: float, copied_mb: float, total_mb: float, speed_mbps: float, current_file: str):
        """Обновляет UI напрямую используя значения в МБ, чтобы избежать переполнения"""
        # Пересчитываем процент из МБ, если переданный процент равен 0 или невалиден
        if total_mb > 0:
            calculated_percent = (copied_mb / total_mb) * 100.0
            # Используем пересчитанный процент, если переданный равен 0 или меньше пересчитанного
            if percent == 0 or calculated_percent > percent:
                percent = calculated_percent
            # Ограничиваем процент от 0 до 100
            percent = max(0, min(100, percent))
        
        # Бар анимируется только к последнему подтверждённому значению.
        self._set_progress_target(percent)
        self._set_percent_label_value(min(percent, 99.0))
        
        # Обновляем скорость
        if speed_mbps > 0:
            self._update_speed_if_due(f"Скорость: {speed_mbps:.2f} МБ/с")
        else:
            self._update_speed_if_due("Скорость: -- МБ/с")
        
        # Обновляем скопированный объём (используем МБ напрямую)
        if total_mb > 0:
            from utils import format_size
            # Конвертируем МБ в байты только для форматирования (с защитой от переполнения)
            try:
                copied_bytes = int(copied_mb * 1048576.0)
                total_bytes = int(total_mb * 1048576.0)
                if copied_bytes < 0 or total_bytes < 0:
                    # Если переполнение, используем МБ напрямую для отображения
                    copied_str = f"{copied_mb:.2f} МБ"
                    total_str = f"{total_mb:.2f} МБ"
                else:
                    copied_str = format_size(copied_bytes)
                    total_str = format_size(total_bytes)
            except (OverflowError, ValueError):
                # Если переполнение, используем МБ напрямую
                copied_str = f"{copied_mb:.2f} МБ"
                total_str = f"{total_mb:.2f} МБ"
            
            self._update_copy_activity(copied_bytes, total_bytes, speed_mbps)
            
            # Обновляем оставшийся объём
            remaining_mb = total_mb - copied_mb
            if remaining_mb > 0:
                try:
                    remaining_bytes = int(remaining_mb * 1048576.0)
                    if remaining_bytes >= 0:
                        remaining_str = format_size(remaining_bytes)
                    else:
                        remaining_str = f"{remaining_mb:.2f} МБ"
                except (OverflowError, ValueError):
                    remaining_str = f"{remaining_mb:.2f} МБ"
            else:
                remaining_str = "0 Б"
            self.remaining_label.setText(f"Осталось: {remaining_str}")
            
            # Вычисляем оставшееся время
            if speed_mbps > 0:
                remaining_seconds = remaining_mb / speed_mbps
                if remaining_seconds < 60:
                    eta_text = f"Осталось времени: ~{int(remaining_seconds)} секунд"
                elif remaining_seconds < 3600:
                    minutes = int(remaining_seconds // 60)
                    seconds = int(remaining_seconds % 60)
                    eta_text = f"Осталось времени: ~{minutes} минут {seconds} секунд"
                else:
                    hours = int(remaining_seconds // 3600)
                    minutes = int((remaining_seconds % 3600) // 60)
                    eta_text = f"Осталось времени: ~{hours} часов {minutes} минут"
                self._update_eta_if_due(eta_text)
            else:
                self._update_eta_if_due("Осталось времени: --")
        else:
            # Если общий объём неизвестен, показываем только скопированный
            try:
                copied_bytes = int(copied_mb * 1048576.0)
                if copied_bytes >= 0:
                    copied_str = format_size(copied_bytes)
                else:
                    copied_str = f"{copied_mb:.2f} МБ"
            except (OverflowError, ValueError):
                copied_str = f"{copied_mb:.2f} МБ"
            self._update_copy_activity(copied_bytes, 0, speed_mbps)
            self.remaining_label.setText("Осталось: --")
            self._update_eta_if_due("Осталось времени: --")
        
        # Обновляем текущий файл
        if current_file and not self.view_model.is_paused:
            file_name = current_file.split('/')[-1] if '/' in current_file else current_file
            self._set_label_text_if_changed(self.current_file_label, file_name)
            self.current_file_label.setToolTip(current_file)
        elif not current_file and not self.view_model.is_paused:
            self._set_label_text_if_changed(self.current_file_label, "Ожидание...")
            self.current_file_label.setToolTip("")
    
    def _update_ui_directly(self, percent: int, copied_bytes: int, total_bytes: int, speed_mbps: float, current_file: str):
        """Обновляет UI напрямую без использования сигналов ViewModel (legacy метод, используйте _update_ui_directly_from_mb)"""
        # Обновляем прогресс-бар
        self.progress_bar.setValue(percent)
        self._set_percent_label_value(percent)
        
        # Обновляем скорость
        if speed_mbps > 0:
            self.speed_label.setText(f"Скорость: {speed_mbps:.2f} МБ/с")
        else:
            self.speed_label.setText("Скорость: -- МБ/с")
        
        # Обновляем скопированный объём
        if total_bytes > 0:
            copied_str = format_size(copied_bytes)
            total_str = format_size(total_bytes)
            self.copied_label.setText(f"Скопировано: {copied_str} из {total_str}")
            
            # Обновляем оставшийся объём
            remaining_bytes = total_bytes - copied_bytes
            remaining_str = format_size(remaining_bytes)
            self.remaining_label.setText(f"Осталось: {remaining_str}")
            
            # Вычисляем оставшееся время
            if speed_mbps > 0:
                remaining_bytes_mb = remaining_bytes / (1024 * 1024)
                remaining_seconds = remaining_bytes_mb / speed_mbps
                if remaining_seconds < 60:
                    self.time_label.setText(f"Осталось времени: ~{int(remaining_seconds)} секунд")
                elif remaining_seconds < 3600:
                    minutes = int(remaining_seconds // 60)
                    seconds = int(remaining_seconds % 60)
                    self.time_label.setText(f"Осталось времени: ~{minutes} минут {seconds} секунд")
                else:
                    hours = int(remaining_seconds // 3600)
                    minutes = int((remaining_seconds % 3600) // 60)
                    self.time_label.setText(f"Осталось времени: ~{hours} часов {minutes} минут")
            else:
                self.time_label.setText("Осталось времени: --")
        else:
            # Если общий объём неизвестен, показываем только скопированный
            copied_str = format_size(copied_bytes)
            self.copied_label.setText(f"Скопировано: {copied_str}")
            self.remaining_label.setText("Осталось: --")
            self.time_label.setText("Осталось времени: --")
        
        # Обновляем текущий файл
        if current_file:
            file_name = current_file.split('/')[-1] if '/' in current_file else current_file
            self.current_file_label.setText(file_name)
            self.current_file_label.setToolTip(current_file)
        else:
            self.current_file_label.setText("Ожидание...")
            self.current_file_label.setToolTip("")
    
    def _on_status_updated(self, message: str):
        """Слот для обработки сигнала обновления статуса (thread-safe) - обновляет ViewModel"""
        self.view_model.update_status(message)
    
    def _on_log_message(self, message: str):
        """Слот для обработки сигнала сообщения лога (thread-safe). Лог процесса удалён из UI — no-op."""
        pass
    
    def show_completion_details(self, stats: dict, status: str):
        """
        Отображает детали завершенного копирования
        
        :param stats: Словарь со статистикой:
            - total_files: int
            - successful_files: int
            - failed_files: int
            - start_time: datetime
            - end_time: datetime
            - total_bytes: int
            - copied_bytes: int
            - destination_path: str
        """
        from datetime import datetime
        
        # Заменяем статистику на детали завершения (один слот). Показываем только самое важное, чтобы влезало в окно.
        self.stats_container.hide()
        self.current_file_container.hide()  # Скрываем секцию "Текущий файл" при завершении
        self.completion_container.show()
        self.completion_title_widget.show()
        self.completion_status_label.show()
        self.completion_stats_label.show()
        self.completion_volume_label.show()
        self.completion_speed_label.show()
        self.completion_destination_label.show()
        # Скрыты намеренно (уменьшаем объём блока): время, источники, категории
        self.completion_time_label.hide()
        self.completion_project_label.hide()
        self.completion_sources_label.hide()
        self.completion_categories_label.hide()
        
        # Статус
        if status == BackupCompletionStatus.SUCCESS.value:
            self.completion_status_label.setText("✅ Копирование завершено успешно")
        elif status == BackupCompletionStatus.WARNING.value:
            self.completion_status_label.setText(
                "⚠️ Резервная копия требует внимания"
            )
        elif status == BackupCompletionStatus.CANCELLED.value:
            self.completion_status_label.setText("⏹ Резервное копирование отменено")
        else:
            failure_message = getattr(self, "_completion_message", "")
            if failure_message and failure_message != "Резервное копирование завершено с ошибками":
                self.completion_status_label.setText(f"❌ {failure_message}")
            else:
                self.completion_status_label.setText(
                    f"❌ Резервное копирование завершено с ошибками "
                    f"({stats.get('failed_files', 0)})"
                )
        
        # Статистика файлов
        total_files = stats.get('total_files', 0)
        successful_files = stats.get('successful_files', 0)
        failed_files = stats.get('failed_files', 0)
        self.completion_stats_label.setText(
            f"Файлов: всего {total_files}, успешно {successful_files}, ошибок {failed_files}"
        )
        
        # Время — не показываем (скрыто для компактности)
        start_time = stats.get('start_time')
        end_time = stats.get('end_time')
        if start_time and end_time:
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time)
        
        # Объем
        total_bytes = stats.get('total_bytes', 0)
        copied_bytes = stats.get('copied_bytes', 0)
        if total_bytes > 0:
            total_str = format_size(total_bytes)
            copied_str = format_size(copied_bytes)
            self.completion_volume_label.setText(f"Объем: скопировано {copied_str} из {total_str}")
        elif copied_bytes > 0:
            copied_str = format_size(copied_bytes)
            self.completion_volume_label.setText(f"Объем: скопировано {copied_str}")
        else:
            self.completion_volume_label.setText("Объем: --")
        
        # Средняя скорость
        if start_time and end_time and copied_bytes > 0:
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time)
            
            duration_seconds = (end_time - start_time).total_seconds()
            if duration_seconds > 0:
                copied_mb = copied_bytes / (1024 * 1024)
                avg_speed = copied_mb / duration_seconds
                self.completion_speed_label.setText(f"Средняя скорость: {avg_speed:.2f} МБ/с")
            else:
                self.completion_speed_label.setText("Средняя скорость: --")
        else:
            self.completion_speed_label.setText("Средняя скорость: --")
        
        # Путь назначения
        destination_path = stats.get('destination_path', '')
        self.destination_path = destination_path  # Сохраняем для использования в кнопке
        if destination_path:
            self.completion_destination_label.setText(f"Путь назначения: {destination_path}")
            self.completion_destination_label.setToolTip(destination_path)
        else:
            self.completion_destination_label.setText("Путь назначения: --")
    
    def _on_finished(self, status: str, message: str, stats: dict = None):
        """Слот для обработки сигнала завершения (thread-safe)"""
        self._completion_message = (message or "").strip()
        self._progress_animation.stop()
        self._speed_update_timer.stop()
        self._eta_update_timer.stop()
        self._pending_speed_text = None
        self._pending_eta_text = None
        self._stop_copy_activity(finalized=True)
        if status == BackupCompletionStatus.SUCCESS.value:
            self._last_confirmed_progress_value = UIAnimation.PROGRESS_SCALE
            self.progress_bar.setValue(UIAnimation.PROGRESS_SCALE)
            self._set_percent_label_value(100)

        # Останавливаем проверку в ViewModel
        self.view_model.stop_verification()
        
        # Останавливаем все таймеры
        self.verification_timer.stop()
        self.pulse_animation_timer.stop()
        self.verification_time_label.setText("")
        
        # Скрываем поля статистики, которые не несут информации после завершения
        self.speed_label.hide()
        self.time_label.hide()
        self.remaining_label.hide()
        self.verification_time_label.hide()
        
        if status in (
            BackupCompletionStatus.SUCCESS.value,
            BackupCompletionStatus.WARNING.value,
            BackupCompletionStatus.FAILED.value,
        ):
            self.setWindowTitle("Прогресс копирования - Завершено")
            # Скрываем кнопки "Пауза" и "Отмена"
            self.pause_button.hide()
            self.cancel_button.hide()
            # Показываем зеленую кнопку "Завершить"
            self.finish_button.show()
            # Показываем кнопку "Открыть папку", если путь назначения доступен
            if stats and stats.get('destination_path'):
                self.open_folder_button.show()
            if external_volumes_for_sources(self.source_paths):
                self.eject_button.show()
            self._refresh_action_buttons_layout()
            # Показываем детали завершения, если статистика передана
            if stats:
                self.show_completion_details(stats, status)
                warnings = stats.get("warnings", [])
                if warnings:
                    self.completion_status_label.setText(
                        "⚠️ Копирование завершено с предупреждениями.\n"
                        + "\n".join(str(warning) for warning in warnings)
                    )
        else:
            self.clear_cancel_pending()
            self.setWindowTitle("Прогресс копирования - Отменено")
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(True)  # чтобы можно было нажать «Закрыть» и закрыть окно сразу
            self.cancel_button.setText("Закрыть")
            # Для отмены тоже можно показать частичную статистику, если есть
            if stats:
                self.show_completion_details(stats, status)
            
            # Автоматическое закрытие окна через 6 секунд после отмены
            # Отменяем предыдущий таймер, если он был установлен
            if self._auto_close_timer is not None:
                self._auto_close_timer.stop()
            
            # Устанавливаем начальный счетчик обратного отсчета
            self._auto_close_countdown = 6
            
            # Изменяем цвет кнопки на красный
            self.cancel_button.setStyleSheet("background-color: #dc3545; color: #FAFAFA;")
            
            # Обновляем текст кнопки с начальным значением счетчика
            self.cancel_button.setText(f"Закрыть ({self._auto_close_countdown})")
            
            # Создаем новый таймер для обновления счетчика каждую секунду
            self._auto_close_timer = QTimer()
            self._auto_close_timer.timeout.connect(self._update_auto_close_countdown)
            self._auto_close_timer.start(1000)  # Обновление каждую секунду (1000 мс)
            self._refresh_action_buttons_layout()
    
    def _on_pause_clicked(self):
        """Обработчик нажатия кнопки Пауза/Возобновить"""
        # Переключаем состояние в ViewModel
        # Сигнал будет обработан в app.py через callback
        if self.view_model.is_paused:
            self.view_model.set_paused(False)
        else:
            self.view_model.set_paused(True)
    
    def _update_auto_close_countdown(self):
        """Обновляет счетчик обратного отсчета на кнопке и закрывает окно при достижении 0"""
        self._auto_close_countdown -= 1
        
        if self._auto_close_countdown > 0:
            # Обновляем текст кнопки с текущим значением счетчика
            self.cancel_button.setText(f"Закрыть ({self._auto_close_countdown})")
        else:
            # Время истекло, останавливаем таймер и закрываем окно
            if self._auto_close_timer is not None:
                self._auto_close_timer.stop()
                self._auto_close_timer = None
            self._request_back()
    
    def _on_cancel_clicked(self):
        """Обработчик нажатия кнопки Отмена (двухшаговая отмена: первый клик — жёлтая кнопка, второй — отмена)."""
        if self.view_model.is_cancelled or not self.pause_button.isEnabled():
            if self._auto_close_timer is not None:
                self._auto_close_timer.stop()
                self._auto_close_timer = None
                self._auto_close_countdown = 0
            self.cancel_button.setStyleSheet("")
            self._request_back()
        else:
            if self.is_cancel_pending():
                self.view_model.set_cancelled(True)
                self.clear_cancel_pending()
            else:
                self.set_cancel_pending(True)
    
    def _on_finish_clicked(self):
        """Обработчик нажатия кнопки Завершить"""
        self._request_back()

    def _on_eject_clicked(self):
        """Извлекает уникальные внешние тома, с которых выполнялось копирование."""
        volumes = external_volumes_for_sources(self.source_paths)
        if not volumes:
            QMessageBox.information(
                self,
                "Извлечение носителей",
                "Среди источников нет подключённых внешних томов.",
            )
            return

        self.eject_button.setEnabled(False)
        results = [eject_volume(volume) for volume in volumes]
        self.eject_button.setEnabled(True)

        successful = [result.volume_path for result in results if result.success]
        failed = [result for result in results if not result.success]
        if not failed:
            self.eject_button.hide()
            self._refresh_action_buttons_layout()
            if self.on_close:
                self.on_close()
            return

        details = "\n".join(
            f"{result.volume_path}: {result.message}" for result in failed
        )
        QMessageBox.warning(
            self,
            "Не все носители извлечены",
            f"Успешно: {len(successful)} из {len(results)}\n\n{details}",
        )
    
    def _on_open_folder_clicked(self):
        """Обработчик нажатия кнопки Открыть папку"""
        if hasattr(self, 'destination_path') and self.destination_path:
            try:
                # Проверяем, что путь существует
                if os.path.exists(self.destination_path):
                    subprocess.run(['open', self.destination_path])
                else:
                    QMessageBox.warning(
                        self,
                        "Ошибка",
                        f"Папка не найдена:\n{self.destination_path}"
                    )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    f"Не удалось открыть папку:\n{str(e)}"
                )
        else:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Путь назначения не указан"
            )
    
    def _on_verification_error(self, source_path: str, destination_path: str, error_message: str):
        """
        Обработчик сигнала ошибки проверки файла (thread-safe)
        Использует DialogHandler для показа диалога
        """
        # Используем DialogHandler для показа диалога
        action = self.dialog_handler.show_verification_dialog(
            source_path, destination_path, error_message, self
        )
        
        # Сохраняем результат в Handler (уже сохранен в show_verification_dialog)
        # Дополнительно устанавливаем для использования с threading.Event
        self.dialog_handler.set_verification_action(source_path, destination_path, action)

    def _on_copy_conflict(self, source_path: str, destination_path: str, filename: str):
        """
        Обработчик сигнала конфликта при копировании (файл уже существует).
        Показывает диалог Заменить / Пропустить / Оставить оба и разблокирует поток копирования.
        """
        result = self.copy_conflict_dialog_handler.show_copy_conflict_dialog(
            source_path, destination_path, filename, self
        )
        self.copy_conflict_dialog_handler.set_copy_conflict_result(result[0], result[1])

    def get_copy_conflict_action(
        self, source_path: str, destination_path: str, filename: str, timeout: float = 300.0
    ):
        """
        Блокирует поток копирования до ответа пользователя в диалоге конфликта.
        Возвращает (action, apply_to_all): action in ('replace', 'skip', 'keep_both').
        """
        return self.copy_conflict_dialog_handler.get_copy_conflict_action(
            source_path, destination_path, filename, timeout
        )
    
    def get_verification_action(self, source_path: str, destination_path: str, timeout: float = 300.0) -> str:
        """
        Получает действие пользователя для ошибки проверки
        Использует DialogHandler для получения действия
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к файлу назначения
        :param timeout: Таймаут ожидания в секундах
        :return: 'recopy', 'skip', или 'cancel'
        """
        return self.dialog_handler.get_verification_action(source_path, destination_path, timeout)


# Обратная совместимость импортов (страница используется как ProgressPage)
ProgressWindow = ProgressPage
