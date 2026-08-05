"""
Модуль для запуска процесса резервного копирования.
BackupStarter управляет созданием компонентов и запуском процесса копирования.
"""

import os
import logging
import threading
from typing import Dict, Callable, Any

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
from progress_window import ProgressPage
from progress_view_model import ProgressViewModel
from verification_dialog_handler import VerificationDialogHandler
from backup_components.progress_batcher import ProgressUpdateBatcher
from backup_components.control_tokens import CancelToken, PauseToken
from engine import start_backup_process


logger = logging.getLogger(__name__)


class BackupStarter:
    """Управляет запуском процесса резервного копирования"""
    
    def __init__(self, app_instance: QWidget):
        """
        Инициализация BackupStarter
        
        :param app_instance: Экземпляр главного окна приложения
        """
        self.app = app_instance
    
    def create_backup_components(self) -> Dict[str, Any]:
        """
        Создает компоненты для бэкапа (pause_event, cancel_token, progress_window)
        
        :return: Словарь с компонентами
        """
        debug_logger = getattr(self.app, 'debug_logger', None)
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:create_backup_components",
                message="create_backup_components() entry",
                hypothesis_id="A"
            )
        # Создаем механизмы управления паузой и отменой
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:create_backup_components",
                message="Before creating pause_event and cancel_token",
                hypothesis_id="A"
            )
        pause_event = threading.Event()
        pause_event.set()  # По умолчанию не на паузе

        cancel_event = threading.Event()
        pause_token = PauseToken(pause_event)
        cancel_token = CancelToken(cancel_event)
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:create_backup_components",
                message="After creating pause_event and cancel_token",
                data={"pause_event_set": pause_event.is_set(), "cancel_token_is_cancelled": cancel_token.is_cancelled()},
                hypothesis_id="A"
            )
        # Создаем ViewModel и Handler
        # ViewModel должен быть создан в главном потоке Qt для правильной работы сигналов
        from PySide6.QtCore import QThread
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:create_backup_components",
                message="Before ProgressViewModel creation",
                hypothesis_id="A"
            )
        view_model = ProgressViewModel()
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:create_backup_components",
                message="After ProgressViewModel creation",
                data={"view_model_exists": view_model is not None, "view_model_thread": str(view_model.thread())},
                hypothesis_id="A"
            )
        # Убеждаемся, что ViewModel находится в главном потоке
        if view_model.thread() != QThread.currentThread():
            if debug_logger:
                debug_logger.log(
                    location="backup_launcher.py:create_backup_components",
                    message="Moving ViewModel to main thread",
                    hypothesis_id="A"
                )
            view_model.moveToThread(QThread.currentThread())
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:create_backup_components",
                message="Before VerificationDialogHandler creation",
                hypothesis_id="A"
            )
        dialog_handler = VerificationDialogHandler()
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:create_backup_components",
                message="After VerificationDialogHandler creation",
                data={"dialog_handler_exists": dialog_handler is not None},
                hypothesis_id="A"
            )
        # Используем страницу прогресса из главного окна (QStackedWidget)
        progress_page = getattr(self.app, 'progress_page', None)
        if progress_page is None:
            raise RuntimeError("AppNew must create progress_page in _create_ui() before backup can run.")
        progress_page.prepare_for_run(
            view_model,
            dialog_handler,
            source_paths=getattr(self.app.state_manager, "source_paths", []),
        )
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:create_backup_components",
                message="After progress_page.prepare_for_run()",
                data={"progress_page_exists": True},
                hypothesis_id="A"
            )
        return {
            'pause_event': pause_event,
            'pause_token': pause_token,
            'cancel_token': cancel_token,
            'view_model': view_model,
            'progress_window': progress_page,
        }
    
    def setup_progress_window_handlers(self, progress_window: ProgressPage,
                                       pause_event: threading.Event,
                                       cancel_token: CancelToken,
                                       view_model: ProgressViewModel) -> None:
        """
        Настраивает обработчики страницы прогресса (пауза, отмена).

        :param progress_window: Страница прогресса (ProgressPage)
        :param pause_event: Событие паузы
        :param cancel_token: Токен отмены
        :param view_model: ViewModel для управления состоянием
        """
        # Обработчик паузы/возобновления
        # ВАЖНО: Этот обработчик вызывается из главного потока Qt (UI поток)
        # threading.Event является thread-safe, операции с ним безопасны из любого потока
        # ViewModel.set_paused() вызывается из главного потока, что безопасно для Qt Signals
        def on_pause_clicked():
            """Обработчик нажатия кнопки Пауза/Возобновить с синхронизацией pause_event и ViewModel"""
            current_paused_state = view_model.is_paused
            logger.debug("Кнопка паузы нажата. Текущее состояние паузы: %s", current_paused_state)
            
            if current_paused_state:
                # Возобновляем копирование
                PauseToken(pause_event).resume()
                view_model.set_paused(False)  # Вызывается из главного потока Qt - безопасно
                logger.info("Копирование возобновлено")
            else:
                # Ставим на паузу
                PauseToken(pause_event).pause()
                view_model.set_paused(True)  # Вызывается из главного потока Qt - безопасно
                logger.info("Копирование приостановлено")
            
            # Проверяем синхронизацию состояния
            pause_event_state = pause_event.is_set()
            view_model_state = not view_model.is_paused
            if pause_event_state != view_model_state:
                logger.warning(
                    "Несоответствие состояния! pause_event.is_set()=%s, not view_model.is_paused=%s",
                    pause_event_state,
                    view_model_state,
                )
        
        # Обработчик отмены (двухшаговая отмена: первый клик — жёлтая кнопка, второй — отмена)
        # ВАЖНО: Этот обработчик вызывается из главного потока Qt (UI поток)
        # threading.Event является thread-safe, операции с ним безопасны из любого потока
        # ViewModel.set_cancelled() вызывается из главного потока, что безопасно для Qt Signals
        def on_cancel_clicked():
            """Обработчик нажатия кнопки Отмена с синхронизацией cancel_token и ViewModel"""
            if view_model.is_cancelled:
                logger.debug("Копирование уже отменено, возврат на главную")
                progress_window._request_back()
                return

            if progress_window.is_cancel_pending():
                cancel_token.cancel()
                view_model.set_cancelled(True)
                progress_window.clear_cancel_pending()
                logger.info("Запрошена отмена копирования")
                cancel_token_state = cancel_token.is_cancelled()
                view_model_state = view_model.is_cancelled
                if cancel_token_state != view_model_state:
                    logger.warning(
                        "Несоответствие состояния отмены! cancel_token.is_cancelled()=%s, view_model.is_cancelled=%s",
                        cancel_token_state,
                        view_model_state,
                    )
                return

            progress_window.set_cancel_pending(True)
        
        # Безопасно отключаем существующие обработчики перед подключением новых
        try:
            progress_window.pause_button.clicked.disconnect()
            logger.debug("Стандартный обработчик кнопки паузы отключен")
        except TypeError:
            # Если обработчик не был подключен, это нормально
            logger.debug("Стандартный обработчик кнопки паузы не был подключен")
        
        try:
            progress_window.cancel_button.clicked.disconnect()
            logger.debug("Стандартный обработчик кнопки отмены отключен")
        except TypeError:
            # Если обработчик не был подключен, это нормально
            logger.debug("Стандартный обработчик кнопки отмены не был подключен")
        
        # Подключаем новые обработчики
        progress_window.pause_button.clicked.connect(on_pause_clicked)
        progress_window.cancel_button.clicked.connect(on_cancel_clicked)
        logger.info("Обработчики кнопок паузы и отмены подключены")
    
    def create_callbacks(self, progress_window: ProgressPage) -> Dict[str, Callable]:
        """
        Создает callback'и для потока копирования (прогресс, логи, диалоги).
        
        :param progress_window: Страница прогресса (ProgressPage)
        :return: Словарь с callback'ами и progress_batcher
        """
        # Создаем батчер для группировки обновлений прогресса (интервал 150мс)
        progress_batcher = ProgressUpdateBatcher(update_interval_ms=150)
        
        # Подключаем сигнал батчера к сигналу окна прогресса
        # Используем QueuedConnection для thread-safe передачи сигналов
        progress_batcher.progress_updated.connect(
            progress_window.signals.progress_updated.emit,
            type=Qt.ConnectionType.QueuedConnection
        )
        
        # Создаем обертку для log_callback, которая отправляет сообщения в окно прогресса
        def log_callback_wrapper(message: str):
            """Обертка для log_callback, отправляющая сообщения в окно прогресса"""
            # Вызываем оригинальный метод log для консоли
            self.app.log(message)
            # Отправляем сообщение в окно прогресса через сигнал
            progress_window.signals.log_message.emit(message)
        
        # Callback при ошибке проверки файла: решение всегда принимает пользователь.
        def verification_action_callback(
            source_path: str, destination_path: str, error_message: str
        ) -> str:
            filename = os.path.basename(source_path)
            log_callback_wrapper(f"Файл не прошёл проверку: {filename}")
            progress_window.dialog_handler.prepare_for_action()
            progress_window.signals.verification_error.emit(
                source_path,
                destination_path,
                error_message,
            )
            return progress_window.dialog_handler.wait_for_action()

        # Callback для конфликта при копировании (файл уже существует): Заменить / Пропустить / Оставить оба
        def copy_conflict_action_callback(
            source_path: str, destination_path: str, filename: str
        ) -> tuple:
            progress_window.signals.copy_conflict.emit(source_path, destination_path, filename)
            return progress_window.get_copy_conflict_action(
                source_path, destination_path, filename
            )
        
        # Обработчик завершения копирования
        def on_finished(status, message, stats=None):
            """Обработчик сигнала завершения копирования"""
            # Останавливаем батчер прогресса при завершении
            if progress_batcher:
                progress_batcher.stop()
            # Обработка уже выполняется в progress_window._on_finished
            # Здесь только восстанавливаем кнопку главного окна
            self.app.check_button_state()
        
        # Подключаем сигнал завершения
        progress_window.signals.finished.connect(on_finished)
        
        return {
            'progress_callback': None,
            'log_callback': log_callback_wrapper,
            'verification_action_callback': verification_action_callback,
            'copy_conflict_action_callback': copy_conflict_action_callback,
            'progress_batcher': progress_batcher
        }
    
    def start_backup_thread(self, destination_root: str,
                            source_drives: list, callbacks: Dict[str, Callable],
                            pause_event: threading.Event,
                            pause_token: PauseToken, cancel_token: CancelToken,
                            signals: Any) -> None:
        """
        Запускает поток копирования

        :param destination_root: Корневая директория назначения
        :param source_drives: Список источников
        :param callbacks: Словарь с callback'ами
        :param pause_event: Событие паузы
        :param pause_token: Токен паузы
        :param cancel_token: Токен отмены
        :param signals: Сигналы для обновления UI
        """
        debug_logger = getattr(self.app, 'debug_logger', None)
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:start_backup_thread",
                message="start_backup_thread() entry",
                hypothesis_id="D"
            )
        # Получаем зависимости из App (должны быть собраны в composition root).
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:start_backup_thread",
                message="Before getting file_system and config",
                hypothesis_id="D"
            )
        file_system = getattr(self.app, 'file_system', None)
        config = getattr(self.app, 'config', None)
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:start_backup_thread",
                message="After getting file_system and config",
                data={"file_system_exists": file_system is not None, "config_exists": config is not None},
                hypothesis_id="D"
            )
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:start_backup_thread",
                message="Before creating thread",
                hypothesis_id="D"
            )
        # Запускаем батчер прогресса перед началом копирования
        progress_batcher = callbacks.get('progress_batcher')
        if progress_batcher:
            progress_batcher.start()
        
        thread = threading.Thread(
            target=start_backup_process,
            args=(
                destination_root,
                source_drives,
                callbacks['log_callback'],
                self.app.prevent_sleep,
                None,
                self.app.create_md_log,
                pause_event,
                pause_token,
                cancel_token,
                callbacks['progress_callback'],
                signals,
                callbacks['verification_action_callback'],
                callbacks.get('copy_conflict_action_callback'),
                config,
                file_system,
                progress_batcher,
                self.app.telegram_client,
                self.app.source_backup_marker_service,
            ),
            daemon=True
        )
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:start_backup_thread",
                message="After creating thread, before thread.start()",
                data={"thread_name": thread.name, "thread_daemon": thread.daemon},
                hypothesis_id="D"
            )
        thread.start()
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:start_backup_thread",
                message="After thread.start()",
                data={"thread_alive": thread.is_alive()},
                hypothesis_id="D"
            )
        logger.info("Поток резервного копирования запущен")
    
    def launch_backup(self, destination_root: str, source_drives: list) -> None:
        """
        Запускает процесс резервного копирования
        
        :param destination_root: Корневая директория назначения
        :param source_drives: Список источников
        """
        debug_logger = getattr(self.app, 'debug_logger', None)
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="launch_backup() entry",
                data={"destination_root": destination_root, "source_drives_count": len(source_drives)},
                hypothesis_id="A,B,C,D,E,F"
            )
        # Создаем компоненты
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="Before create_backup_components()",
                hypothesis_id="A"
            )
        components = self.create_backup_components()
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="After create_backup_components()",
                data={"components_keys": list(components.keys()), "progress_window_exists": components.get('progress_window') is not None},
                hypothesis_id="A"
            )
        pause_event = components['pause_event']
        pause_token = components['pause_token']
        cancel_token = components['cancel_token']
        view_model = components['view_model']
        progress_window = components['progress_window']

        # Проверяем начальное состояние
        logger.debug(
            "Начальное состояние: pause_event.is_set()=%s, view_model.is_paused=%s, cancel_token.is_cancelled()=%s, view_model.is_cancelled=%s",
            pause_event.is_set(),
            view_model.is_paused,
            cancel_token.is_cancelled(),
            view_model.is_cancelled,
        )

        # Настраиваем обработчики (ВАЖНО: до запуска потока копирования)
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="Before setup_progress_window_handlers()",
                hypothesis_id="B"
            )
        self.setup_progress_window_handlers(progress_window, pause_event, cancel_token, view_model)
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="After setup_progress_window_handlers()",
                hypothesis_id="B"
            )
        # Проверяем, что обработчики подключены
        logger.debug("Обработчики настроены, готовы к запуску копирования")
        
        # Создаем callback'и
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="Before create_callbacks()",
                hypothesis_id="C"
            )
        callbacks = self.create_callbacks(progress_window)
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="After create_callbacks()",
                data={"callbacks_keys": list(callbacks.keys())},
                hypothesis_id="C"
            )
        # Запускаем поток
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="Before start_backup_thread()",
                hypothesis_id="D"
            )
        self.start_backup_thread(
            destination_root,
            source_drives,
            callbacks,
            pause_event,
            pause_token,
            cancel_token,
            progress_window.signals,
        )
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="After start_backup_thread()",
                hypothesis_id="D"
            )
        # Переключаем главное окно на страницу прогресса фиксированной высоты.
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="Before start_transition_to_progress()",
                hypothesis_id="E"
            )
        self.app.start_transition_to_progress()
        if debug_logger:
            debug_logger.log(
                location="backup_launcher.py:launch_backup",
                message="After start_transition_to_progress()",
                hypothesis_id="E"
            )
