#!/bin/bash
# Сборка Dублёр для теста на другом компьютере.
# Результат: архив dist/Dублёр_test_YYYY-MM-DD.zip с приложением и инструкцией.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Dублёр.app"
DATE_SUFFIX="$(date +%Y-%m-%d)"
ARCHIVE_NAME="Dублёр_test_${DATE_SUFFIX}.zip"
DIST_ARCHIVE="dist/${ARCHIVE_NAME}"

echo "🧪 Сборка для теста на другом компьютере"
echo "========================================"
echo ""

# Запускаем производственную сборку
./build.sh

echo ""
echo "📦 Упаковка в архив для переноса..."

# Копируем инструкцию в dist и упаковываем .app + инструкцию в zip
if [ -f "TEST_BUILD_README.md" ]; then
    cp TEST_BUILD_README.md "dist/КАК_ЗАПУСТИТЬ_НА_ДРУГОМ_ПК.txt"
fi

cd dist
zip -r -y "$ARCHIVE_NAME" "$APP_NAME"
[ -f "КАК_ЗАПУСТИТЬ_НА_ДРУГОМ_ПК.txt" ] && zip -y "$ARCHIVE_NAME" "КАК_ЗАПУСТИТЬ_НА_ДРУГОМ_ПК.txt"
cd ..

echo ""
echo "✅ Готово!"
echo ""
echo "📁 Файл для переноса: $DIST_ARCHIVE"
du -sh "$DIST_ARCHIVE"
echo ""
echo "→ Скопируйте этот zip на другой Mac, распакуйте и запустите Dублёр.app"
echo "→ В архиве есть файл КАК_ЗАПУСТИТЬ_НА_ДРУГОМ_ПК.txt с инструкцией."
echo ""
