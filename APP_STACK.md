# Из чего состоит приложение Dублёр

Краткое описание стека и архитектуры для поиска информации в интернете.

---

## Название и назначение

**Dублёр** — десктопное приложение для **резервного копирования** данных для видеооператоров и фотографов. **Только macOS.**

---

## Технологический стек

| Компонент | Технология | Для поиска в интернете |
|-----------|------------|------------------------|
| **Язык** | Python 3.11 / 3.12 | `Python 3.11`, `Python 3.12` |
| **GUI** | PySide6 (Qt для Python) | `PySide6`, `Qt6 Python`, `Qt widgets` |
| **Стиль Qt** | Fusion | `QApplication setStyle Fusion`, `Qt Fusion style` |
| **Сборка в .app** | PyInstaller | `PyInstaller macOS`, `PyInstaller .app bundle` |
| **Системные вызовы** | psutil | `psutil`, `prevent sleep macOS`, `process parent` |
| **HTTP / уведомления** | requests | `requests`, `Telegram Bot API` |
| **Парсинг JSON потоком** | ijson | `ijson`, `streaming JSON` |
| **Тесты** | pytest | `pytest` |

---

## Архитектура и паттерны

- **Dependency Injection (DI)** — зависимости собираются в `composition.py` (composition root), передаются через конструкторы.
- **Интерфейсы (Protocol)** — в `interfaces.py`: `IConfig`, `IFileSystemInterface`, `IFileCopier`, `IFileVerifier`, `IDebugLogger` и др.
- **Repository** — работа с ФС через `FileSystemRepository` в `repositories/`.
- **ViewModel** — отдельная логика состояния для главного окна и прогресса (`MainWindowViewModel`, `ProgressViewModel`).
- **Strategy** — этапы бэкапа в `backup_stages.py`, выбор способа копирования в `copy_strategy.py`.
- **Observer** — сигналы Qt для обновления UI из фоновых потоков.

**Поисковые запросы:** `Python Dependency Injection`, `Python Protocol interface`, `Qt PySide6 ViewModel`, `Repository pattern Python`, `Strategy pattern Python`.

---

## Ключевые возможности (для поиска решений)

1. **Копирование файлов** — `shutil` и блочное копирование больших файлов; прогресс, пауза, отмена.
2. **Проверка целостности** — MD5 и проверка по размеру; кэш хешей (hash storage), дедупликация по MD5.
3. **Контрольные точки и возобновление** — сохранение прогресса, продолжение после прерывания.
4. **GUI** — главное окно (`ui_new/`), окно прогресса, окно настроек, диалоги (в т.ч. Qt UI-формы `.ui`).
5. **Drag and Drop** — источники и папка назначения.
6. **Предотвращение сна** — во время копирования на macOS (через `psutil`/системные API).
7. **Уведомления** — Telegram (Bot API) и системные уведомления macOS (Notification Center).
8. **Темы** — светлая/тёмная (`themes.py`).

**Запросы:** `Python file copy progress cancel`, `MD5 verification Python`, `Qt PySide6 drag and drop`, `macOS prevent sleep Python`, `PyInstaller macOS .app`, `Qt Fusion style dark theme`.

---

## Структура кода (кратко)

- **Точка входа:** `app.py` → `build_app_context()` из `composition.py` → главное окно `AppNew` из `ui_new.main_window_new`.
- **Бизнес-логика бэкапа:** `engine.py`, `backup_launcher.py`, `backup_process_controller.py`, папка `backup_components/` (orchestrator, file_copier, file_verifier, deduplication, hash_storage, retry, progress и т.д.).
- **UI:** `ui/`, `ui_new/`, `widgets/`, `ui_forms/` (диалоги + `.ui` файлы).
- **Конфиг и темы:** `config.py`, `themes.py`.
- **Инфраструктура:** `interfaces.py`, `composition.py`, `repositories/`, `paths.py`, `logger.py`, `notifications.py`, `sleep_prevention.py`.

---

## Готовые поисковые фразы

- `PySide6 Qt6 Python macOS application`
- `PyInstaller onefile macOS .app bundle`
- `Python backup file copy with progress pause cancel`
- `Python MD5 hash verification large files`
- `Qt Fusion style checkbox custom color dark theme`
- `Python dependency injection composition root`
- `macOS prevent system sleep during long task Python`
- `Telegram Bot API send message Python requests`
- `Qt drag and drop files folders PySide6`
- `Python resume interrupted file copy checkpoint`
