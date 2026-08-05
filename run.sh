#!/bin/bash
# Универсальный запуск Dублёр: использует .venv, если есть, иначе python3.
# Решает проблему "command not found: python" на macOS, где часто доступен только python3.

BASE_DIR=$(dirname "$0")
cd "$BASE_DIR" || exit 1

if [ -f ".venv/bin/activate" ]; then
    source ".venv/bin/activate"
    exec python app.py "$@"
fi

if command -v python3 >/dev/null 2>&1; then
    exec python3 app.py "$@"
fi

echo "Ошибка: Python не найден. Установите Python 3.11 или 3.12 (python.org) или создайте venv:"
echo "  python3 -m venv .venv"
echo "  .venv/bin/pip install -r requirements.txt"
echo "  ./run.sh"
exit 1
