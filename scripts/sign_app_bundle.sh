#!/bin/bash
# Подпись .app бандла для macOS (ad-hoc).
# На Apple Silicon и современных macOS все Mach-O должны быть подписаны хотя бы ad-hoc,
# иначе при dlopen возможен краш EXC_BAD_ACCESS (Code Signature Invalid).
# Использование: ./scripts/sign_app_bundle.sh /path/to/Dублёр.app

set -e

if [ $# -lt 1 ]; then
    echo "Использование: $0 <путь к .app>"
    exit 1
fi

APP_PATH="$1"

if [ ! -d "$APP_PATH" ]; then
    echo "Ошибка: не найден каталог $APP_PATH"
    exit 1
fi

# Ad-hoc подпись: -s -
IDENTITY="-"
# --timestamp=none чтобы не обращаться к серверам Apple при ad-hoc
# Hardened runtime не нужен для ad-hoc подписи (требуется только для notarization с платным аккаунтом)

echo "Подпись всех Mach-O в бандле (ad-hoc)..."

# 1) Сначала все вложенные бинарники (Frameworks: Python, .so, .dylib), чтобы при подписи бандла подписи были валидны
if [ -d "$APP_PATH/Contents/Frameworks" ]; then
    find "$APP_PATH/Contents/Frameworks" -type f -print0 2>/dev/null | while IFS= read -r -d '' f; do
        if file "$f" 2>/dev/null | grep -q Mach-O; then
            codesign -s "$IDENTITY" --force --timestamp=none "$f" 2>/dev/null || true
        fi
    done
fi

# 2) Главный исполняемый файл
MAIN_EXE=$(find "$APP_PATH/Contents/MacOS" -maxdepth 1 -type f -perm -111 2>/dev/null | head -1)
if [ -n "$MAIN_EXE" ]; then
    codesign -s "$IDENTITY" --force --timestamp=none "$MAIN_EXE"
fi

# 3) Сам .app бандл
codesign -s "$IDENTITY" --force --timestamp=none "$APP_PATH"

echo "Подпись завершена."
