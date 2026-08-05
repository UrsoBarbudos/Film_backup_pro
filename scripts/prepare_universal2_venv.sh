#!/bin/bash
# Создание .venv_universal2 для сборки universal2.
# Требуется Python с python.org (universal2), не Homebrew.
# Использование: ./scripts/prepare_universal2_venv.sh [путь_к_python3]
# Пример: ./scripts/prepare_universal2_venv.sh /Library/Frameworks/Python.framework/Versions/3.12/bin/python3

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -n "$1" ]; then
    PYTHON="$1"
else
    # Попытка найти python.org: типичный путь на macOS
    for p in /Library/Frameworks/Python.framework/Versions/*/bin/python3; do
        if [ -x "$p" ]; then
            PYTHON="$p"
            break
        fi
    done
fi

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    echo "Использование: $0 /путь/к/python3"
    echo "Установите Python 3.11 или 3.12 с https://www.python.org/downloads/ (macOS universal2)."
    exit 1
fi

echo "Python: $PYTHON"
$PYTHON --version
echo ""

if [ -d "$PROJECT_ROOT/.venv_universal2" ]; then
    echo ".venv_universal2 уже существует. Пересоздать? (y/N)"
    read -r ans
    if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
        echo "Выход."
        exit 0
    fi
    rm -rf "$PROJECT_ROOT/.venv_universal2"
fi

echo "Создание .venv_universal2..."
"$PYTHON" -m venv "$PROJECT_ROOT/.venv_universal2"
echo "Установка зависимостей..."
if ! "$PROJECT_ROOT/.venv_universal2/bin/pip" install -r requirements.txt --quiet; then
    echo "Повтор с --trusted-host (обход SSL)..."
    "$PROJECT_ROOT/.venv_universal2/bin/pip" install -r requirements.txt --quiet \
        --trusted-host pypi.org --trusted-host files.pythonhosted.org
fi
echo ""
echo "Готово. Дальше: ./scripts/check_universal2_lipo.sh и ./build.sh"
