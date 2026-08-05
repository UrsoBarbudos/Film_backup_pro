"""
Основной файл Dублёр (PySide6 версия)
"""

import sys
import os
import logging
import subprocess
from pathlib import Path

from composition import build_app_context

logger = logging.getLogger(__name__)


def main():
    """Точка входа в приложение"""
    # В собранном .app при запуске из терминала/IDE (родитель — shell/IDE) на macOS 26
    # HIServices вызывает abort() при регистрации приложения. Ре-запуск через open
    # даёт процесс с родителем launchd, регистрация проходит, крэш не возникает.
    if getattr(sys, "frozen", False) and sys.argv:
        _argv0 = sys.argv[0]
        _p = Path(_argv0).resolve()
        if "Contents/MacOS" in str(_p):
            _bundle_path = str(_p.parent.parent.parent)
            _parent_name = ""
            try:
                import psutil  # type: ignore[reportMissingImports]
                _parent_name = (psutil.Process(os.getppid()).name() or "").lower()
            except Exception:
                pass
            _terminal_like = _parent_name in ("cursor", "zsh", "bash", "python", "python3", "terminal", "electron", "cmd")
            if _bundle_path and _terminal_like:
                try:
                    subprocess.run(["open", "-n", _bundle_path], check=True, timeout=5)
                except Exception:
                    pass
                sys.exit(0)
    # Ранняя инициализация стандартного logging (до потоков/бэкапа).
    # Уровень: env DUBLER_LOG_LEVEL имеет приоритет над config.
    # Собираем зависимости в одном месте (composition root).
    # Делается максимально рано, чтобы context был доступен legacy-адаптерам (на время миграции).
    context = build_app_context()

    try:
        from paths import get_debug_log_path
        from logger import configure_logging, get_effective_log_level

        config_level = context.config.get("log_level", "INFO") if context.config else "INFO"
        configure_logging(
            log_file_path=get_debug_log_path(),
            level=get_effective_log_level(str(config_level)),
            console=True,
        )
    except Exception:
        # Если конфигурация логирования не поднялась, продолжаем запускать приложение.
        pass

    try:
        from PySide6.QtWidgets import QApplication  # type: ignore[reportMissingImports]
        app = QApplication(sys.argv)

        # Устанавливаем стиль Fusion (поддерживает к!"астомные стили для чекбоксов)
        # Стиль macOS блокирует изменение цвета индикатора чекбокса
        app.setStyle("Fusion")

        from ui_new.main_window_new import AppNew
        window = AppNew(context=context)            

        window.show()

        sys.exit(app.exec())
    except Exception as e:
        logger.exception("Failed to start application: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
