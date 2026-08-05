#!/bin/bash
# Единый скрипт сборки и упаковки Dублёр
# Собирает universal2 приложение и упаковывает его в DMG с установщиком

set -e

# Защита от случайного запуска временных файлов
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
if [[ "$SCRIPT_NAME" == "tempCodeRunnerFile.sh" ]] || [[ "$SCRIPT_NAME" == *"temp"* ]]; then
    echo "❌ Ошибка: этот скрипт не должен запускаться как временный файл"
    echo "   Используйте: ./build.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Dублёр.app"
APP_PATH="dist/$APP_NAME"
BUILT_APP_PATH="dist/Dubler.app"
EXE_PATH="$APP_PATH/Contents/MacOS/Dubler"
DATE_SUFFIX="$(date +%Y-%m-%d)"

echo "🏭 Сборка и упаковка Dублёр"
echo "===================================="
echo ""

# Проверка Python окружения
PYTHON_CMD="$SCRIPT_DIR/.venv_universal2/bin/python"
if [ ! -x "$PYTHON_CMD" ]; then
    echo "❌ Ошибка: не найден .venv_universal2/bin/python"
    echo ""
    echo "Подготовка окружения для universal2:"
    echo "  1. Установите Python 3.11 или 3.12 с https://www.python.org/downloads/ (macOS universal2)"
    echo "  2. Создайте venv: ./scripts/prepare_universal2_venv.sh /путь/к/python3"
    echo "  3. Проверьте архитектуры: ./scripts/check_universal2_lipo.sh"
    exit 1
fi

# Сборка приложения
echo "🔨 Сборка приложения (universal2)"
echo "----------------------------------------"
echo "Используется Python: $PYTHON_CMD"
$PYTHON_CMD --version
echo ""

echo "📦 Проверка зависимостей..."
if ! $PYTHON_CMD -c "import PySide6" 2>/dev/null; then
    echo "⚠️  PySide6 не найден. Устанавливаем зависимости..."
    $PYTHON_CMD -m pip install -r requirements.txt --quiet
else
    echo "✅ Зависимости установлены"
fi
echo ""

echo "🧹 Очистка предыдущих сборок..."
rm -rf build dist || true
echo ""

echo "🔨 Запуск сборки (Dублёр_universal2.spec)..."
$PYTHON_CMD -m PyInstaller --noconfirm "Dублёр_universal2.spec"

if [ ! -d "$BUILT_APP_PATH" ]; then
    echo "❌ Ошибка: приложение не было создано"
    exit 1
fi

mv "$BUILT_APP_PATH" "$APP_PATH"

APP_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_PATH/Contents/Info.plist")"
if [ -z "$APP_VERSION" ]; then
    echo "❌ Ошибка: в собранном приложении не указана версия"
    exit 1
fi
DMG_VOLUME_NAME="Dubler_${APP_VERSION}_${DATE_SUFFIX}"
DMG_OUTPUT="dist/${DMG_VOLUME_NAME}.dmg"
echo "🏷️  Версия сборки: $APP_VERSION"

echo "✅ Сборка завершена!"
echo ""

# Подпись приложения (один раз после сборки)
if [ "$(uname)" = "Darwin" ]; then
    echo "✍️  Подпись приложения (ad-hoc)..."
    xattr -c "$APP_PATH" 2>/dev/null || true
    "$SCRIPT_DIR/scripts/sign_app_bundle.sh" "$APP_PATH"
fi

echo "📐 Архитектура:"
file "$EXE_PATH" 2>/dev/null || true
echo "📏 Размер:"
du -sh "$APP_PATH"
echo ""

# Создание DMG
echo "📦 Создание DMG"
echo "----------------------------------------"
echo ""

# Временная папка для содержимого DMG
DMG_TEMP_DIR=$(mktemp -d -t dubler_dmg.XXXXXX)
trap 'rm -rf "$DMG_TEMP_DIR"' EXIT

# Копирование файлов в DMG
echo "📦 Подготовка содержимого DMG..."
cp -R "$APP_PATH" "$DMG_TEMP_DIR/"

DMG_INSTRUCTION_SRC="$SCRIPT_DIR/scripts/dmg_how_to_run.txt"
INSTRUCTION_FILE="$DMG_TEMP_DIR/КАК_ЗАПУСТИТЬ.txt"
if [ -f "$DMG_INSTRUCTION_SRC" ]; then
    cp "$DMG_INSTRUCTION_SRC" "$INSTRUCTION_FILE"
    chmod 644 "$INSTRUCTION_FILE"
else
    touch "$INSTRUCTION_FILE"
    chmod 644 "$INSTRUCTION_FILE"
fi

UNLOCK_SCRIPT_SRC="$SCRIPT_DIR/scripts/РАЗБЛОКИРОВАТЬ_И_ЗАПУСТИТЬ.command"
UNLOCK_SCRIPT_FILE="$DMG_TEMP_DIR/РАЗБЛОКИРОВАТЬ_И_ЗАПУСТИТЬ.command"
if [ -f "$UNLOCK_SCRIPT_SRC" ]; then
    cp "$UNLOCK_SCRIPT_SRC" "$UNLOCK_SCRIPT_FILE"
    chmod 755 "$UNLOCK_SCRIPT_FILE"
fi

ln -s /Applications "$DMG_TEMP_DIR/Программы"

# Создание DMG напрямую в сжатом формате
echo "💾 Создание DMG образа..."
[ -f "$DMG_OUTPUT" ] && rm -f "$DMG_OUTPUT"
hdiutil create -srcfolder "$DMG_TEMP_DIR" -volname "$DMG_VOLUME_NAME" \
    -fs HFS+ -format UDZO -imagekey zlib-level=9 -ov "$DMG_OUTPUT"

# Подпись DMG файла
if [ "$(uname)" = "Darwin" ]; then
    echo "✍️  Подпись DMG (ad-hoc)..."
    codesign -s - --force --timestamp=none "$DMG_OUTPUT" 2>/dev/null || true
fi

echo ""
echo "===================================="
echo "✅ Готово!"
echo "===================================="
echo ""
echo "📦 DMG создан: $DMG_OUTPUT"
du -sh "$DMG_OUTPUT"
echo ""
echo "📋 Содержимое DMG:"
echo "   • Dублёр.app — приложение (universal2)"
echo "   • КАК_ЗАПУСТИТЬ.txt — инструкция по установке"
echo "   • РАЗБЛОКИРОВАТЬ_И_ЗАПУСТИТЬ.command — обход блокировки Gatekeeper"
echo "   • Программы — ссылка для установки"
echo ""
echo "📤 Готово к распространению!"
echo ""
