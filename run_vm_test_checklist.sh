#!/bin/bash
# Чеклист для тестирования Dублёр в виртуальной машине.
# Запустите на хосте после сборки — скрипт выведет пути и команду для гостевой macOS.
# Подробнее: VM_TESTING.md

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Dублёр.app"
APP_PATH="dist/$APP_NAME"
DMG_PATH="dist/Dubler.dmg"

echo "=============================================="
echo "  Чеклист теста Dублёр в виртуальной машине"
echo "=============================================="
echo ""

if [ ! -d "$APP_PATH" ]; then
    echo "❌ Приложение не найдено. Сначала выполните: ./build.sh"
    echo "   Или: ./create_dmg.sh --build"
    exit 1
fi

ARCH=$(file "dist/$APP_NAME/Contents/MacOS/Dублёр" 2>/dev/null | grep -o 'arm64\|x86_64' || echo "?")
echo "📦 Архитектура сборки: $ARCH"
echo ""

echo "1. На хосте — что перенести в ВМ (один из вариантов):"
echo "   • Папка приложения:"
echo "     $SCRIPT_DIR/$APP_PATH"
echo "   • Или образ DMG (как у пользователя):"
if [ -f "$DMG_PATH" ]; then
    echo "     $SCRIPT_DIR/$DMG_PATH"
else
    echo "     (создайте: ./create_dmg.sh)"
fi
echo ""

echo "2. В гостевой macOS — после копирования:"
echo "   • Запуск: двойной клик по Dублёр.app"
echo "   • Или в Терминале (подставьте свой путь к приложению):"
echo "     open \"/путь/к/Dублёр.app\""
echo "   ⚠️  Не запускайте Contents/MacOS/Dублёр напрямую (SIGABRT на macOS 26)."
echo ""

echo "3. При первом запуске (Gatekeeper):"
echo "   Системные настройки → Безопасность и конфиденциальность → «Всё равно открыть»."
echo ""

echo "4. Логи в гостевой системе:"
echo "   ~/Library/Logs/Dubler/debug.log  или  Консоль (Console.app)."
echo ""

echo "=============================================="
