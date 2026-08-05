# Методы (Film_backup_pro / Dублёр)

Краткое описание публичных и ключевых внутренних методов по модулям.

---

## app.py

| Метод | Описание |
|-------|----------|
| **main()** | Точка входа: сбор контекста (`build_app_context`), настройка логирования, создание QApplication и главного окна `AppNew`, запуск цикла Qt. |

---

## backup_components/backup_orchestrator.py

| Метод | Описание |
|-------|----------|
| **create()** | Фабрика оркестратора из `BackupRunConfig`, `BackupTokens`, `BackupCallbacks`, `BackupDeps` (без legacy-конструктора). |
| **run()** | Запуск бэкапа: последовательное выполнение этапов (Initialization → Copying → Verification → Finalization), обработка отмены и ошибок, cleanup. |
| **_check_cancellation()** | Проверка `cancel_token`; при отмене — `BackupCancelledError`. |
| **_check_pause()** | Ожидание снятия паузы через `pause_token.wait_if_paused(cancel_token)`. |
| **copy_conflict_policy** | Текущая политика при конфликте: `'replace' | 'skip' | 'keep_both'` или None; сбрасывается в начале этапа копирования. |

---

## backup_components/deduplication_manager.py

| Метод | Описание |
|-------|----------|
| **compute_sample_signature()** | Вычисляет sample_signature файла (size + first/last chunk, blake2b). |
| **get_or_compute_sample_signature()** | Берёт из HashStorage или вычисляет и кэширует sample_signature. |
| **compute_md5()** | Вычисляет MD5 с адаптивным размером блока и учётом cancel. |
| **get_or_compute_md5()** | Берёт MD5 из HashStorage или вычисляет и сохраняет. |

---

## backup_components/file_copier.py

| Метод | Описание |
|-------|----------|
| **copy_file()** | Копирует один файл: при существовании в назначении — перезапись (решение о замене/пропуске/оставить оба принимается в CopyPlanAndExecuteService через диалог); выбор SHUTIL/BLOCK, копирование с подсчётом MD5, сохранение хеша в HashStorage, очистка при ошибке. |
| **_copy_with_shutil()** | Копирование блоками 1 МБ для файлов < 100 МБ с подсчётом MD5 по ходу. |
| **_copy_with_blocks()** | Блочное копирование с адаптивным блоком (10/15/20 МБ), прогрессом и паузой/отменой, MD5 по ходу. |

---

## backup_components/file_verifier.py

| Метод | Описание |
|-------|----------|
| **verify_file()** | Проверка пары исход/назначение: в режиме `fast` — по размеру, в `full` — трёхфазная (размер → sample_signature → MD5). |
| **_verify_by_checksum()** | Level A (размер) → B (sample_signature) → C (MD5), с использованием HashStorage. |
| **_verify_by_size()** | Сравнение только размеров исходного и целевого файла. |

---

## backup_components/hash_storage.py

| Метод | Описание |
|-------|----------|
| **set_hash()** | Сохраняет MD5 и метаданные файла, обновляет `hash_index`, при достижении порога — автосохранение. |
| **get_hash()** | Возвращает сохранённый MD5 по пути файла. |
| **get_sample_signature()** / **set_sample_signature()** | Чтение/запись sample_signature и параметров (chunk_size). |
| **_load()** / **_load_normal()** / **_load_streaming()** | Загрузка хранилища (обычное или потоковое через ijson для больших файлов). |
| **_save()** / **_save_unlocked()** | Сохранение с блокировкой, атомарная запись во временный файл и replace. |
| **cleanup_temp_files()** | Удаление временных файлов хранилища. |

---

## backup_components/copy_strategy.py

| Метод | Описание |
|-------|----------|
| **get_copy_method(file_size)** | Функция: возвращает `CopyMethod.SHUTIL` или `CopyMethod.BLOCK` в зависимости от размера файла (порог 100 МБ). |

---

## backup_components/retry_handler.py

| Метод | Описание |
|-------|----------|
| **RetryHandler.retry_on_temporary_error(func, *args, **kwargs)** | Выполняет функцию с повторами при временных ошибках (задержка, лимит попыток). Использует `is_temporary_error` из `backup_components/exceptions.py`. |

---

## backup_components/progress_batcher.py

| Метод | Описание |
|-------|----------|
| **update_progress()** | Обновляет состояние прогресса из фонового потока (thread-safe), выставляет флаг и при необходимости запускает таймер. |
| **_emit_batched_update()** | Отправляет накопленное обновление в UI по сигналу (вызов из главного потока по таймеру). |
| **start()** / **stop()** | Запуск/остановка таймера батчинга; при stop при необходимости отправляется последнее обновление. |
| **force_update()** | Принудительная отправка текущего прогресса в главный поток через `QMetaObject.invokeMethod`. |

---

## backup_components/backup_stages.py

| Метод | Описание |
|-------|----------|
| **BackupStage.execute(orchestrator)** | Абстрактный метод этапа. |
| **InitializationStage.execute()** | Sleep prevention, сканирование объёма, инициализация проекта. |
| **CopyingStage.execute()** | Вызов `_copy_all_files()`. |
| **VerificationStage.execute()** | Вызов `_verify_all_files()`. |
| **FinalizationStage.execute()** | Вызов `_finalize_process()`. |

---

## backup_components/orchestrator_services/copy_plan_and_execute_service.py

| Метод | Описание |
|-------|----------|
| **copy_all_files()** | Сброс `copy_conflict_policy`, обход источников; для файла/папки вызывает process_single_file / process_directory. |
| **process_single_file()** | Проверка системного файла, подготовка назначения, разрешение конфликта (_resolve_destination_conflict), копирование одного файла. |
| **_resolve_destination_conflict()** | Если файл в назначении существует: запрос действия (политика или copy_conflict_action_callback); skip → None, replace → dst_file, keep_both → уникальный путь. |
| **_generate_unique_path_in_dir()** | Генерирует уникальный путь в папке (имя_1.ext, имя_2.ext, …) для действия «Оставить оба». |
| **prepare_file_destination()** | Формирование пути назначения (структура папок; при существовании пути конфликт обрабатывается в _resolve_destination_conflict). |
| **handle_single_file_copy()** | Вызов file_copier, валидация, учёт результата и статистики. |

---

## backup_components/orchestrator_services/verification_service.py

| Метод | Описание |
|-------|----------|
| **verify_all_files()** | Обход `files_to_verify`, вызов верификатора, обработка ошибок (retry/recopy/skip/cancel). |
| **handle_verification_failure()** | Запрос действия у пользователя, при необходимости перекопирование и повторная проверка. |

---

## engine_modules/scanning.py

| Метод | Описание |
|-------|----------|
| **scan_sources_unified()** | Единое сканирование источников, возврат `ScanResult` (total_size, total_files, files_list, source_sizes). |
| **scan_total_size()** | Обёртка над `scan_sources_unified`, возвращает только `total_size`. |

---

## engine_modules/categories.py

| Метод | Описание |
|-------|----------|
| **get_file_category(filename)** | Video/Audio/Photo по расширению. |
| **is_system_file(filename)** | Признаёт системные файлы macOS (.DS_Store, ._*, и т.д.). |
| **get_folder_predominant_category()** | Преобладающая категория по содержимому папки. |

---

## speed_calculator.py

| Метод | Описание |
|-------|----------|
| **SpeedCalculator.update(current_speed)** | Обновление EMA скорости; при current_speed ≤ 0 EMA не меняется. |
| **get_speed()** | Текущая сглаженная скорость (МБ/с). |
| **reset()** | Сброс EMA и флага инициализации. |

---

## control_tokens (по использованию в коде)

| Метод | Описание |
|-------|----------|
| **CancelToken.is_cancelled()** / **raise_if_cancelled()** | Проверка и выброс при отмене. |
| **PauseToken.is_paused()** / **wait_if_paused(cancel_token)** | Проверка паузы и ожидание с учётом отмены. |

---

## utils.py

| Метод | Описание |
|-------|----------|
| **resolve_file_system()** | Проверка, что передан не `None` IFileSystemInterface. |
| **get_directory_size()** | Рекурсивный размер директории с опциональной отменой. |
| **safe_add_bytes()** | Сложение байт с защитой от переполнения. |
| **format_size()** | Форматирование размера для вывода пользователю. |

---

## config.py

| Метод | Описание |
|-------|----------|
| **load()** / **save()** | Загрузка и сохранение настроек (в т.ч. атомарная запись и миграция). |
| **get(key, default)** / **set(key, value)** | Доступ к настройкам. |

---

## composition.py

| Метод | Описание |
|-------|----------|
| **build_app_context()** | Сборка контекста приложения (config, file_system, сервисы бэкапа, launcher и т.д.) — composition root. |
