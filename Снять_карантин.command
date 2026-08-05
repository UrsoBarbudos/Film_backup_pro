#!/bin/bash
# Снять карантин с Dублёр — запустите этот файл двойным кликом, если Mac блокирует приложение.

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Dублёр.app"

# Сначала ищем приложение в той же папке, что и этот скрипт (например, в открытом DMG)
APP_PATH="$DIR/$APP_NAME"
if [ ! -d "$APP_PATH" ]; then
    # Если уже перетащили в «Программы»
    APP_PATH="/Applications/$APP_NAME"
fi

if [ -d "$APP_PATH" ]; then
    if xattr -cr "$APP_PATH" 2>/dev/null; then
        echo "Готово. Карантин снят с Dублёр."
    else
        # На некоторых системах xattr не поддерживает -r, снимаем только с самой папки
        xattr -c "$APP_PATH" 2>/dev/null && echo "Готово. Атрибуты сняты с Dублёр."
    fi
else
    echo "Не найден $APP_NAME"
    echo "Положите этот файл в ту же папку, что и приложение, и запустите снова."
fi

echo ""
echo "Нажмите Enter для закрытия..."
read -r
