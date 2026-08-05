#!/bin/bash
# Запустить Dублёр — снимает карантин и сразу открывает приложение. Запустите двойным кликом при первом запуске.

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Dублёр.app"

APP_PATH="$DIR/$APP_NAME"
if [ ! -d "$APP_PATH" ]; then
    APP_PATH="/Applications/$APP_NAME"
fi

if [ ! -d "$APP_PATH" ]; then
    echo "Не найден $APP_NAME"
    echo "Положите этот файл в ту же папку, что и приложение, и запустите снова."
    echo ""
    echo "Нажмите Enter для закрытия..."
    read -r
    exit 1
fi

if xattr -cr "$APP_PATH" 2>/dev/null; then
    echo "Карантин снят, запускаю Dублёр."
else
    xattr -c "$APP_PATH" 2>/dev/null || true
    echo "Запускаю Dублёр."
fi

open "$APP_PATH"

echo ""
echo "Нажмите Enter для закрытия..."
read -r
