#!/bin/bash
# Установить Dублёр — копирует в «Программы» и настраивает для запуска
# Запустите двойным кликом из открытого DMG.

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Dублёр.app"
APP_PATH="$DIR/$APP_NAME"

# Проверка наличия приложения
if [ ! -d "$APP_PATH" ]; then
    osascript -e 'display dialog "Не найден Dублёр.app в этой папке.\n\nЗапустите этот файл из открытого DMG (там же, где лежит приложение)." buttons {"OK"} default button "OK" with icon stop' 2>/dev/null || {
        echo "Не найден $APP_NAME в этой папке."
        echo "Запустите этот файл из открытого DMG (там же, где лежит приложение)."
        echo ""
        echo "Нажмите Enter для закрытия..."
        read -r
    }
    exit 1
fi

# Диалог подтверждения установки
osascript -e 'display dialog "Установить Dублёр в папку «Программы»?\n\nПриложение будет скопировано и настроено для запуска." buttons {"Отмена", "Установить"} default button "Установить" with icon question' 2>/dev/null || {
    echo "Установка отменена пользователем."
    exit 0
}

echo "Установка Dублёр"
echo "===================================="
echo ""

# Папка назначения
DEST="/Applications"
if [ ! -w "/Applications" ] 2>/dev/null; then
    DEST="$HOME/Applications"
    if [ ! -d "$DEST" ]; then
        mkdir -p "$DEST"
    fi
fi

# Проверка существующей установки
if [ -d "$DEST/$APP_NAME" ]; then
    osascript -e 'display dialog "Dублёр уже установлен в «Программы».\n\nЗаменить существующую версию?" buttons {"Отмена", "Заменить"} default button "Заменить" with icon question' 2>/dev/null || {
        echo "Установка отменена пользователем."
        exit 0
    }
    echo "Удаление старой версии..."
    rm -rf "$DEST/$APP_NAME"
fi

# --- 1) Копирование в «Программы» ---
osascript -e 'display notification "Копирование Dублёр в «Программы»..." with title "Установка Dублёр"' 2>/dev/null || true
echo "1. Копирование в «Программы»..."
if ! cp -R "$APP_PATH" "$DEST/"; then
    osascript -e 'display dialog "Ошибка копирования.\n\nПроверьте права доступа к папке «Программы»." buttons {"OK"} default button "OK" with icon stop' 2>/dev/null || {
        echo "   Ошибка копирования. Проверьте права доступа к $DEST"
        echo ""
        echo "Нажмите Enter для закрытия..."
        read -r
    }
    exit 1
fi
INSTALLED_APP="$DEST/$APP_NAME"
echo "   Готово: $INSTALLED_APP"
echo ""

# --- 2) Подпись приложения (ad-hoc) ---
osascript -e 'display notification "Подпись приложения..." with title "Установка Dублёр"' 2>/dev/null || true
echo "2. Подпись приложения (ad-hoc)..."
IDENTITY="-"

# Пытаемся использовать скрипт подписи, если доступен
SCRIPT_DIR="$(dirname "$0")"
SIGN_SCRIPT="$SCRIPT_DIR/../scripts/sign_app_bundle.sh"

if [ -f "$SIGN_SCRIPT" ]; then
    # Используем скрипт подписи
    "$SIGN_SCRIPT" "$INSTALLED_APP" 2>/dev/null || {
        echo "   Предупреждение: не удалось использовать скрипт подписи, используется базовая"
        codesign -s "$IDENTITY" --force --timestamp=none "$INSTALLED_APP" 2>/dev/null || true
    }
else
    # Fallback: базовая ad-hoc подпись вручную
    if [ -d "$INSTALLED_APP/Contents/Frameworks" ]; then
        find "$INSTALLED_APP/Contents/Frameworks" -type f -print0 2>/dev/null | while IFS= read -r -d '' f; do
            if file "$f" 2>/dev/null | grep -q Mach-O; then
                codesign -s "$IDENTITY" --force --timestamp=none "$f" 2>/dev/null || true
            fi
        done
    fi
    MAIN_EXE=$(find "$INSTALLED_APP/Contents/MacOS" -maxdepth 1 -type f -perm -111 2>/dev/null | head -1)
    if [ -n "$MAIN_EXE" ]; then
        codesign -s "$IDENTITY" --force --timestamp=none "$MAIN_EXE" 2>/dev/null || true
    fi
    codesign -s "$IDENTITY" --force --timestamp=none "$INSTALLED_APP" 2>/dev/null || true
fi
echo "   Подпись выполнена."
echo ""

# --- 3) Снятие карантина у установленной копии ---
osascript -e 'display notification "Снятие карантина..." with title "Установка Dублёр"' 2>/dev/null || true
echo "3. Снятие атрибутов карантина..."
xattr -cr "$INSTALLED_APP" 2>/dev/null || xattr -c "$INSTALLED_APP" 2>/dev/null || true
echo "   Готово."
echo ""

# Успешное завершение
osascript -e 'display dialog "Установка завершена!\n\nDублёр установлен в «Программы».\n\nТеперь можно запускать приложение двойным кликом." buttons {"OK"} default button "OK" with icon note' 2>/dev/null || {
    echo ""
    echo "===================================="
    echo "Установка завершена."
    echo ""
    echo "Запустите Dублёр из папки «Программы» (или через Spotlight)."
    echo ""
    echo "Нажмите Enter для закрытия..."
    read -r
}
