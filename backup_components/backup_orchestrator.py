"""
Модуль для координации процесса резервного копирования.
BackupOrchestrator координирует работу всех компонентов процесса копирования.
"""

import logging
import threading
import uuid
import warnings
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional, Callable, Any, TYPE_CHECKING

from interfaces import IConfig, IFileSystemInterface, IFileCopier, IFileVerifier
from engine_modules.category_definitions import (
    CATEGORY_DEFINITIONS,
)

if TYPE_CHECKING:
    from engine_modules.scanning import ScanResult

from .backup_logger import BackupLogger
from .backup_notifier import BackupNotifier
from .backup_run_context import BackupCallbacks, BackupDeps, BackupRunConfig, BackupTokens
from .backup_stages import (
    CopyingStage,
    FinalizationStage,
    InitializationStage,
    VerificationStage,
)
from .control_tokens import CancelToken, PauseToken
from .exceptions import BackupCancelledError
from .file_copier import FileCopier
from .file_verifier import FileVerifier
from .hash_storage import HashStorage
from .completion_status import BackupCompletionStatus
from .operation_issue import (
    OperationIssue,
    OperationIssueCode,
    create_message_issue,
    create_operation_issue,
)
from .orchestrator_services import (
    CompletionService,
    CopyPlanAndExecuteService,
    ProgressReportingService,
    DestinationInitializationService,
    VerificationService,
)
from .retry_handler import RetryHandler

logger = logging.getLogger(__name__)


class BackupOrchestrator:
    """Класс для координации процесса резервного копирования"""
    
    @classmethod
    def create(
        cls,
        run: BackupRunConfig,
        tokens: BackupTokens,
        callbacks: BackupCallbacks,
        deps: BackupDeps,
    ) -> "BackupOrchestrator":
        """
        Новый «чистый» путь создания оркестратора: контексты + зависимости.

        Важно: не вызывает legacy `__init__`, чтобы не тащить 20+ параметров по всему коду.
        """
        self = cls.__new__(cls)
        self._init_from_context(run=run, tokens=tokens, callbacks=callbacks, deps=deps)
        return self

    def __init__(
        self,
        destination_root: str,
        source_drives: List[str],
        log_callback: Callable[[str], None],
        prevent_sleep: bool = True,
        success_callback: Optional[Callable] = None,
        create_md_log: bool = False,
        pause_event: Optional[threading.Event] = None,
        pause_token: Optional[PauseToken] = None,
        cancel_token: Optional[CancelToken] = None,
        progress_callback: Optional[Callable] = None,
        signals: Optional[Any] = None,
        verification_action_callback: Optional[Callable] = None,
        config: Optional[IConfig] = None,
        file_system: Optional[IFileSystemInterface] = None,
        verification_mode: Optional[str] = None,
        file_copier: Optional[IFileCopier] = None,
        file_verifier: Optional[IFileVerifier] = None,
        progress_batcher: Optional[Any] = None
    ):
        """
        Инициализация оркестратора
        
        :param destination_root: Корневая директория назначения
        :param source_drives: Список дисков-источников
        :param log_callback: Функция для логирования
        :param prevent_sleep: Если True, предотвращает спящий режим во время копирования
        :param success_callback: Callback функция, вызываемая после успешного завершения
        :param create_md_log: Если True, создает MD лог-файл после завершения
        :param pause_event: threading.Event для управления паузой
        :param progress_callback: Callback функция для обновления прогресса
        :param signals: Объект ProgressSignals для thread-safe обновления UI
        :param verification_action_callback: Callback функция для запроса действия пользователя при ошибке проверки
        :param config: Экземпляр Config (опционально)
        :param file_system: Интерфейс файловой системы (опционально)
        :param verification_mode: Режим проверки файлов - 'full' (MD5) или 'fast' (размер). Если None, берется из config
        :param file_copier: Интерфейс для копирования файлов (опционально, создается автоматически если не передан)
        :param file_verifier: Интерфейс для проверки файлов (опционально, создается автоматически если не передан)
        :param progress_batcher: Батчер для группировки обновлений прогресса (опционально)
        """
        warnings.warn(
            "BackupOrchestrator.__init__(...) is deprecated; use BackupOrchestrator.create(...) with dataclass contexts.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Получаем режим проверки из config, если не передан явно
        if verification_mode is None:
            verification_mode = config.get("verification_mode", "full") if config else "full"

        run = BackupRunConfig(
            destination_root=destination_root,
            source_drives=list(source_drives),
            verification_mode=verification_mode,
            create_md_log=create_md_log,
            prevent_sleep=prevent_sleep,
        )
        tokens = BackupTokens.from_legacy(
            pause_event=pause_event,
            pause_token=pause_token,
            cancel_token=cancel_token,
        )
        callbacks = BackupCallbacks(
            log_callback=log_callback,
            progress_callback=progress_callback,
            signals=signals,
            verification_action_callback=verification_action_callback,
            copy_conflict_action_callback=None,
            success_callback=success_callback,
            progress_batcher=progress_batcher,
        )
        deps = BackupDeps(
            file_system=file_system,  # type: ignore[arg-type]
            config=config,
            file_copier=file_copier,
            file_verifier=file_verifier,
        )

        self._init_from_context(run=run, tokens=tokens, callbacks=callbacks, deps=deps)

    def _init_from_context(
        self,
        *,
        run: BackupRunConfig,
        tokens: BackupTokens,
        callbacks: BackupCallbacks,
        deps: BackupDeps,
    ) -> None:
        self.destination_root = run.destination_root
        self.source_drives = run.source_drives
        self.verification_mode = run.verification_mode
        self.create_md_log = run.create_md_log
        self.prevent_sleep = run.prevent_sleep

        self.log_callback = callbacks.log_callback
        self.progress_callback = callbacks.progress_callback
        self.progress_batcher = callbacks.progress_batcher
        self.signals = callbacks.signals
        self.verification_action_callback = callbacks.verification_action_callback
        self.copy_conflict_action_callback = getattr(
            callbacks, "copy_conflict_action_callback", None
        )
        self.success_callback = callbacks.success_callback
        self.copy_conflict_policy: Optional[str] = None

        self.pause_event = tokens.pause_event
        self.pause_token = tokens.pause_token
        self.cancel_token = tokens.cancel_token

        # Интерфейс файловой системы должен передаваться явно.
        # Для обратной совместимости оставляем возможность None, но без импорта factories.
        if deps.file_system is None:
            raise ValueError(
                "file_system must be provided (use composition root and pass dependencies explicitly)."
            )
        self.file_system = deps.file_system
        self.config = deps.config
        self.source_backup_marker_service = deps.source_backup_marker_service

        self._sleep_prevention_factory = deps.sleep_prevention_factory

        # Инициализируем RetryHandler для обработки временных ошибок
        self.retry_handler = deps.retry_handler or RetryHandler(
            max_attempts=3,
            delay=1.0,
            log_callback=self.log_callback,
        )

        # Инициализируем HashStorage для кэширования хешей файлов
        self.hash_storage = deps.hash_storage or HashStorage(
            config=deps.config,
            file_system=self.file_system,
            cancel_token=self.cancel_token,
        )

        self.verification_run_id = uuid.uuid4().hex

        # Инициализация компонентов (используем переданные интерфейсы или создаем по умолчанию)
        if deps.file_copier is None:
            self.file_copier = FileCopier(
                log_callback=self.log_callback,
                file_system=self.file_system,
                pause_event=self.pause_event,
                pause_token=self.pause_token,
                cancel_token=self.cancel_token,
                hash_storage=self.hash_storage,
                verification_mode=self.verification_mode,
                verification_run_id=self.verification_run_id,
            )
        else:
            self.file_copier = deps.file_copier

        if deps.file_verifier is None:
            self.file_verifier = FileVerifier(
                log_callback=self.log_callback,
                file_system=self.file_system,
                cancel_token=self.cancel_token,
                verification_mode=self.verification_mode,
                hash_storage=self.hash_storage,
                verification_run_id=self.verification_run_id,
            )
        else:
            self.file_verifier = deps.file_verifier

        self.backup_logger = deps.backup_logger or BackupLogger()
        self.backup_notifier = deps.backup_notifier or BackupNotifier(
            log_callback=self.log_callback,
            config=deps.config,
            file_system=self.file_system,
            telegram_client=deps.telegram_client,
        )

        # Менеджеры
        self.sleep_manager = None

        # Состояние процесса
        self.start_time = datetime.now()
        self.end_time = None
        self.total_bytes = 0
        self.copied_bytes = 0
        self.total_files = 0
        self.successful_files = 0
        self.failed_files = 0
        self.operation_issues: list[OperationIssue] = []
        self._operation_issue_keys: set[tuple] = set()
        self.skipped_files = 0
        self.skipped_bytes = 0
        self.copy_plan_completed = False
        self.current_file = ""
        self.last_update_time = self.start_time
        self.last_copied_bytes = 0

        # Результат единого сканирования
        if TYPE_CHECKING:
            from engine_modules.scanning import ScanResult
        self.scan_result: Optional['ScanResult'] = None

        # Данные текущего запуска
        self.all_files_to_copy = []
        self.verified_files_set: Set[str] = set()
        self.current_stage = "copying"
        self.files_to_verify: List[Tuple] = []
        self.destination_index_by_size: Optional[Any] = None
        self.copied_files: Dict[str, List[Dict[str, str]]] = {
            definition.key: [] for definition in CATEGORY_DEFINITIONS
        }

        # Сервисы (логика этапов)
        self._destination_initialization_service = DestinationInitializationService()
        self._copy_plan_and_execute_service = CopyPlanAndExecuteService()
        self._verification_service = VerificationService()
        self._progress_reporting_service = ProgressReportingService()
        self._completion_service = CompletionService()

    @property
    def verification_read_bytes(self) -> int:
        """Фактические байты полных чтений назначения при проверке."""
        return int(getattr(self.file_copier, "verification_read_bytes", 0)) + int(
            getattr(self.file_verifier, "verification_read_bytes", 0)
        )
    
    def _create_pause_event(self) -> threading.Event:
        """Создает и инициализирует событие паузы"""
        event = threading.Event()
        event.set()  # По умолчанию не на паузе
        return event

    def record_issue(
        self,
        issue: OperationIssue,
        *,
        count_failure: bool = True,
        emit_status: bool = True,
    ) -> bool:
        """Регистрирует окончательную ошибку один раз и синхронизирует счётчик."""
        key = (
            issue.stage,
            issue.code,
            issue.source_path,
            issue.destination_path,
            issue.file_name,
            issue.technical_message,
            issue.fatal,
        )
        if key in self._operation_issue_keys:
            return False
        self._operation_issue_keys.add(key)
        self.operation_issues.append(issue)
        if count_failure:
            self.failed_files += 1
        if emit_status and self.signals:
            try:
                self.signals.status_updated.emit(f"❌ {issue.message}")
            except Exception:  # noqa: BLE001 - ошибка UI не скрывает файловую
                logger.debug("Не удалось отправить статус ошибки в UI", exc_info=True)
        return True

    def run(self) -> None:
        """
        Запускает процесс резервного копирования.
        Координирует все этапы: инициализация, копирование, проверка, логирование, уведомления.
        Использует паттерн Strategy для разделения этапов процесса.
        """
        logger.debug("BackupOrchestrator.run() entry")
        self._log_start()
        
        # Определяем последовательность этапов
        stages = [
            InitializationStage(),
            CopyingStage(),
        ]
        stages.append(VerificationStage())
        stages.append(FinalizationStage())
        logger.debug("Executing stages (count=%d)", len(stages))
        
        try:
            # Выполняем каждый этап последовательно
            for stage in stages:
                # Проверка отмены перед выполнением каждого этапа
                self._check_cancellation()
                logger.debug("Stage start: %s", type(stage).__name__)
                stage.execute(self)
                logger.debug("Stage end: %s", type(stage).__name__)
            
        except BackupCancelledError:
            logger.info("Backup cancelled")
            self._handle_cancellation()
            raise
        except Exception as e:
            logger.exception("Exception in BackupOrchestrator.run()")
            self._handle_error(e)
            raise
        finally:
            self._cleanup()
            logger.debug("BackupOrchestrator.run(): cleanup complete")
    
    def _log_start(self) -> None:
        """Логирует начало процесса"""
        logger.info("%s", "=" * 60)
        logger.info("Запуск процесса резервного копирования")
        logger.info("Корневая директория назначения: %s", self.destination_root)
        logger.info("Количество источников: %d", len(self.source_drives))
        logger.info(
            "Предотвращение спящего режима: %s",
            "включено" if self.prevent_sleep else "выключено",
        )
        logger.info(
            "Создание MD лог-файла: %s",
            "включено" if self.create_md_log else "выключено",
        )
        logger.info("%s", "=" * 60)
        self.log_callback("––– Запуск резервного копирования –––")
    
    def _initialize_sleep_prevention(self) -> None:
        """Инициализирует предотвращение спящего режима"""
        self._destination_initialization_service.initialize_sleep_prevention(self)
    
    def _scan_total_size(self) -> None:
        """Выполняет предварительное сканирование для подсчета общего объема"""
        self._destination_initialization_service.scan_total_size(self)
    
    def _initialize_destination(self) -> None:
        """Проверяет выбранную пользователем папку назначения."""
        self._destination_initialization_service.initialize_destination(self)

    def _copy_all_files(self) -> None:
        """Копирует все файлы из источников"""
        self._copy_plan_and_execute_service.copy_all_files(self)
    
    def _process_single_file(self, source_path: str) -> None:
        """Обрабатывает отдельный файл"""
        self._copy_plan_and_execute_service.process_single_file(self, source_path)
    
    def _prepare_file_destination(self, source_path: str, filename: str, category: str) -> Optional[str]:
        """
        Подготавливает путь назначения для файла
        
        :return: Путь к файлу назначения или None если ошибка
        """
        return self._copy_plan_and_execute_service.prepare_file_destination(
            self, source_path, filename, category
        )
    
    def _generate_unique_filename(self, dest_dir: str, filename: str, file_number: int) -> Optional[str]:
        """
        Генерирует уникальное имя файла если файл с таким именем уже существует
        
        :return: Уникальное имя файла или None
        """
        return self._copy_plan_and_execute_service.generate_unique_filename(
            self, dest_dir, filename, file_number
        )
    
    def _handle_single_file_copy(self, source_path: str, dst_file: str, filename: str, category: str) -> None:
        """
        Выполняет копирование одного файла
        
        :param source_path: Путь к исходному файлу
        :param dst_file: Путь к файлу назначения
        :param filename: Имя файла
        :param category: Категория файла
        """
        self._copy_plan_and_execute_service.handle_single_file_copy(
            self, source_path, dst_file, filename, category
        )
    
    def _validate_copied_file(
        self, 
        src_file: str, 
        dst_file: str, 
        filename: str, 
        category: Optional[str] = None,
        update_copied_bytes: bool = False,
        log_success: bool = False
    ) -> bool:
        """
        Валидирует скопированный файл (проверяет размер)
        
        :param src_file: Путь к исходному файлу
        :param dst_file: Путь к файлу назначения
        :param filename: Имя файла
        :param category: Категория файла (если None, вычисляется автоматически)
        :param update_copied_bytes: Если True, обновляет copied_bytes
        :param log_success: Если True, логирует сообщение об успехе
        :return: True если файл валиден, False в противном случае
        """
        return self._copy_plan_and_execute_service.validate_copied_file(
            self,
            src_file=src_file,
            dst_file=dst_file,
            filename=filename,
            category=category,
            update_copied_bytes=update_copied_bytes,
            log_success=log_success,
        )
    
    def _validate_single_file_copy(self, source_path: str, dst_file: str, filename: str, category: str) -> None:
        """
        Валидирует скопированный файл (проверяет размер)
        
        :param source_path: Путь к исходному файлу
        :param dst_file: Путь к файлу назначения
        :param filename: Имя файла
        :param category: Категория файла
        """
        self._copy_plan_and_execute_service.validate_single_file_copy(
            self, source_path, dst_file, filename, category
        )
    
    def _process_directory(self, source_path: str) -> None:
        """Обрабатывает директорию (рекурсивно)"""
        self._copy_plan_and_execute_service.process_directory(self, source_path)
    
    def _determine_folder_structure(self, dirpath: str, source_path: str, disk_name: str) -> Tuple[str, str, Tuple[str, str]]:
        """
        Определяет структуру папок для файла
        
        :param dirpath: Путь к директории с файлом
        :param source_path: Путь к исходной папке
        :param disk_name: Имя исходной папки
        :return: (root_folder, subfolder_path, folder_key)
        """
        return self._copy_plan_and_execute_service.determine_folder_structure(
            self, dirpath, source_path, disk_name
        )
    
    def _get_or_assign_folder_number(self, folder_key: Tuple[str, str], category: str) -> int:
        """
        Получает или присваивает номер для папки
        Нумерация уникальна для категории
        
        :param folder_key: Ключ папки (source_path, root_folder)
        :param category: Категория файлов
        :return: Номер папки
        """
        return self._copy_plan_and_execute_service.get_or_assign_folder_number(
            self, folder_key, category
        )
    
    def _copy_file_from_directory(self, src_file: str, dst_file: str, filename: str, category: str) -> None:
        """
        Копирует один файл из директории
        
        :param src_file: Путь к исходному файлу
        :param dst_file: Путь к файлу назначения
        :param filename: Имя файла
        :param category: Категория файла
        """
        self._copy_plan_and_execute_service.copy_file_from_directory(
            self, src_file, dst_file, filename, category
        )
    
    def _handle_file_copy_result(self, src_file: str, dst_file: str, filename: str, 
                                 category: str, success: bool, file_size: int, source_hash: Optional[str] = None) -> None:
        """
        Обрабатывает результат копирования файла
        
        :param src_file: Путь к исходному файлу
        :param dst_file: Путь к файлу назначения
        :param filename: Имя файла
        :param category: Категория файла
        :param success: Успешно ли скопирован файл
        :param file_size: Размер скопированного файла
        :param source_hash: MD5 хеш исходного файла (опционально)
        """
        self._copy_plan_and_execute_service.handle_file_copy_result(
            self, src_file, dst_file, filename, category, success, file_size, source_hash
        )
    
    def _validate_file_copy(self, src_file: str, dst_file: str, filename: str) -> bool:
        """
        Валидирует скопированный файл (проверяет размер)
        
        :return: True если файл валиден
        """
        return self._copy_plan_and_execute_service.validate_file_copy(self, src_file, dst_file, filename)
    
    def _save_file_info_for_log(self, dst_file: str, category: str, file_size: int) -> None:
        """Сохраняет информацию о файле для MD лог-файла"""
        self._copy_plan_and_execute_service.save_file_info_for_log(self, dst_file, category, file_size)
    
    def _verify_all_files(self) -> None:
        """Проверяет целостность всех скопированных файлов"""
        self._verification_service.verify_all_files(self)
    
    def _is_file_already_verified(self, src_file: str, filename: str) -> bool:
        """
        Проверяет, был ли файл уже проверен
        
        :return: True если файл уже проверен
        """
        return self._verification_service.is_file_already_verified(self, src_file, filename)
    
    def _update_verification_progress(self, verify_index: int, total_files: int, filename: str) -> None:
        """
        Обновляет прогресс проверки
        
        :param verify_index: Индекс текущего файла
        :param total_files: Всего файлов для проверки
        :param filename: Имя файла
        """
        self._progress_reporting_service.update_verification_progress(
            self, verify_index, total_files, filename
        )
    
    def _handle_verification_failure(
        self,
        src_file: str,
        dst_file: str,
        filename: str,
        issue: OperationIssue,
    ) -> bool:
        """
        Обрабатывает ошибку проверки файла
        
        :return: True если нужно продолжить, False если отменено
        """
        return self._verification_service.handle_verification_failure(
            self, src_file, dst_file, filename, issue
        )
    
    def _retry_file_copy(
        self, src_file: str, dst_file: str, filename: str
    ) -> Optional[OperationIssue]:
        """
        Повторно копирует файл при ошибке проверки
        
        :return: None при успехе или актуальная ошибка повторной попытки
        """
        return self._verification_service.retry_file_copy(self, src_file, dst_file, filename)
    
    def _get_verification_action(
        self,
        source_path: str,
        destination_path: str,
        issue: OperationIssue,
    ) -> str:
        """
        Запрашивает действие пользователя при ошибке проверки через UI
        Возвращает 'recopy', 'skip', или 'cancel'
        """
        return self._verification_service.get_verification_action(
            self, source_path, destination_path, issue
        )
    
    def _update_progress(self) -> None:
        """Обновляет прогресс копирования"""
        self._progress_reporting_service.update_progress(self)
    
    def _check_cancellation(self) -> None:
        """
        Проверяет флаг отмены и прерывает выполнение при необходимости
        
        ВАЖНО: Этот метод вызывается из фонового потока копирования.
        threading.Event.is_set() является thread-safe операцией.
        """
        if self.cancel_token.is_cancelled():
            logger.debug("_check_cancellation() - отмена запрошена (cancel_token.is_cancelled()), прерываем выполнение")
            self.log_callback("❌ Копирование отменено пользователем")
            raise BackupCancelledError("Копирование отменено пользователем")
    
    def _check_pause(self) -> None:
        """
        Проверяет флаг паузы и ожидает возобновления при необходимости
        
        ВАЖНО: Этот метод вызывается из фонового потока копирования.
        threading.Event.is_set() и threading.Event.wait() являются thread-safe операциями.
        pause_event управляется из главного потока Qt через обработчики кнопок.
        """
        pause_event_state = self.pause_event.is_set()
        logger.debug("_check_pause(): pause_event_state=%s", pause_event_state)
        if not pause_event_state:
            logger.debug("_check_pause() - pause_event не установлен, ставим на паузу")
            self.log_callback("⏸️  Копирование приостановлено...")
            logger.debug("_check_pause() - ожидаем возобновления (PauseToken.wait_if_paused)")
            # Важно: wait_if_paused проверяет cancel, поэтому cancel сработает даже на паузе.
            self.pause_token.wait_if_paused(self.cancel_token)
            logger.debug("_check_pause() - pause_event установлен, возобновляем выполнение")
            self.log_callback("▶️  Копирование возобновлено")
    
    def _finalize_process(self) -> None:
        """Завершает процесс: создает логи, отправляет уведомления"""
        self._completion_service.finalize_process(self)
    
    def _update_final_progress(self) -> None:
        """Обновляет финальный прогресс"""
        self._progress_reporting_service.update_final_progress(self)
    
    def _prepare_completion_stats(self) -> Dict:
        """
        Подготавливает статистику завершения
        
        :return: Словарь со статистикой
        """
        return self._completion_service.prepare_completion_stats(self)
    
    def _emit_completion_signal(self, stats: Dict) -> None:
        """Отправляет сигнал о завершении с статистикой"""
        self._completion_service.emit_completion_signal(self, stats)
    
    def _emit_fallback_completion_signal(self) -> None:
        """Отправляет сигнал о завершении без статистики (fallback)"""
        self._completion_service.emit_fallback_completion_signal(self)
    
    def _prepare_stats_safely(self) -> Optional[Dict]:
        """Безопасно подготавливает единую статистику через CompletionService."""
        return self._completion_service.prepare_completion_stats_safely(self)
    
    def _print_completion_summary(self) -> None:
        """Выводит итоговую информацию о завершении"""
        logger.info("%s", "=" * 60)
        logger.info("Резервное копирование завершено!")
        logger.info("Всего файлов: %d", self.total_files)
        logger.info("Успешно скопировано: %d", self.successful_files)
        logger.info("Ошибок: %d", self.failed_files)
        logger.info("%s", "=" * 60)
    
    def _create_md_log_if_needed(self) -> Optional[str]:
        """
        Создает MD лог-файл если необходимо
        
        :return: Путь к созданному лог-файлу или None
        """
        return self._completion_service.create_md_log_if_needed(self)
    
    def _send_completion_notifications(self, stats: Dict, log_path: Optional[str]) -> None:
        """
        Отправляет уведомления о завершении копирования
        
        :param stats: Статистика завершения
        :param log_path: Путь к лог-файлу
        """
        self._completion_service.send_completion_notifications(self, stats, log_path)
    
    def _call_success_callback(self) -> None:
        """Вызывает callback после успешного завершения"""
        self._completion_service.call_success_callback(self)
    
    def _handle_cancellation(self) -> None:
        """Обрабатывает отмену процесса"""
        self.log_callback("❌ Копирование прервано")
        self.end_time = datetime.now()
        self.record_issue(
            create_message_issue(
                stage=self.current_stage,
                code=OperationIssueCode.CANCELLED,
                message="Резервное копирование отменено пользователем",
                source_path=self.current_file or None,
                destination_path=self.destination_root,
                file_name=(
                    self.file_system.basename(self.current_file)
                    if self.current_file
                    else None
                ),
            ),
            count_failure=False,
            emit_status=False,
        )
        self._create_emergency_md_log()
        if not self.signals:
            return
        
        stats = self._prepare_stats_safely()
        try:
            self.signals.finished.emit(
                BackupCompletionStatus.CANCELLED.value,
                "Копирование отменено пользователем",
                stats,
            )
        except Exception:
            pass
    
    def _handle_error(self, error: Exception) -> None:
        """Обрабатывает ошибки процесса"""
        error_msg = f"❌ Критическая ошибка при копировании: {error}"
        logger.exception("%s", error_msg)
        self.log_callback(error_msg)
        self.end_time = datetime.now()
        issue = create_operation_issue(
            error,
            stage=self.current_stage or "finalization",
            source_path=self.current_file or None,
            destination_path=self.destination_root,
            file_name=(
                self.file_system.basename(self.current_file)
                if self.current_file
                else None
            ),
            fatal=True,
            message="Резервное копирование остановлено из-за критической ошибки",
        )
        self.record_issue(issue, emit_status=False)
        self._create_emergency_md_log(force=True)
        if not self.signals:
            return
        
        stats = self._prepare_stats_safely()
        try:
            self.signals.finished.emit(
                BackupCompletionStatus.FAILED.value, issue.message, stats
            )
        except Exception:
            pass

    def _create_emergency_md_log(self, *, force: bool = False) -> Optional[str]:
        """Best-effort отчёт без рекурсивной обработки ошибок отчёта."""
        create_md_log_before = self.create_md_log
        try:
            if force:
                self.create_md_log = True
            path = self._completion_service.create_md_log_if_needed(self)
            report_issue = getattr(self.backup_logger, "last_issue", None)
            if report_issue is not None:
                self.record_issue(
                    report_issue,
                    count_failure=False,
                    emit_status=False,
                )
            return path
        except Exception as report_error:  # noqa: BLE001
            logger.exception(
                "Не удалось создать аварийный Markdown-отчёт: %s", report_error
            )
            return None
        finally:
            self.create_md_log = create_md_log_before
    
    def _cleanup(self) -> None:
        """Очищает ресурсы после завершения процесса"""
        # Останавливаем батчер прогресса и отправляем финальное обновление
        if self.progress_batcher:
            self.progress_batcher.stop()
        
        # Очищаем временные файлы HashStorage
        if self.hash_storage:
            try:
                self.hash_storage.cleanup_temp_files()
            except Exception as e:
                logger.warning("Не удалось очистить временные файлы HashStorage: %s", e)
        
        # Завершаем предотвращение спящего режима, если было включено
        if self.sleep_manager:
            self.sleep_manager.__exit__(None, None, None)
            self.log_callback("Предотвращение спящего режима выключено")
