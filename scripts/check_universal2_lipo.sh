#!/bin/bash
# Проверка архитектур в .venv_universal2 (lipo) перед сборкой universal2.
# Запуск: из корня проекта — ./scripts/check_universal2_lipo.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VENV_PYTHON="$PROJECT_ROOT/.venv_universal2/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "Ошибка: не найден .venv_universal2/bin/python"
    echo "Создайте окружение: см. BUILD_INSTRUCTIONS.md, раздел «Сборка universal2», шаги 1.1–1.2."
    exit 1
fi

echo "Проверка архитектур (lipo) для universal2..."
echo ""

# Python
PYEXE=$("$VENV_PYTHON" -c "import sys; print(sys.executable)")
echo "1. Python: $PYEXE"
lipo -info "$PYEXE" 2>/dev/null || echo "   (lipo не сработал)"
echo ""

# stdlib
BASE=$("$VENV_PYTHON" -c "import sys; print(sys.base_prefix)")
STRUCT=$(find "$BASE/lib/python"* -name "_struct*.so" 2>/dev/null | head -1)
if [ -n "$STRUCT" ] && [ -f "$STRUCT" ]; then
    echo "2. stdlib (_struct): $STRUCT"
    lipo -info "$STRUCT" 2>/dev/null || echo "   (lipo не сработал)"
else
    echo "2. stdlib (_struct): не найден"
fi
echo ""

# psutil
PSUTIL_SO=$(find "$PROJECT_ROOT/.venv_universal2/lib/python"* -path "*psutil*_psutil_osx*" -name "*.so" 2>/dev/null | head -1)
if [ -n "$PSUTIL_SO" ] && [ -f "$PSUTIL_SO" ]; then
    echo "3. psutil: $PSUTIL_SO"
    lipo -info "$PSUTIL_SO" 2>/dev/null || echo "   (lipo не сработал)"
    if lipo -info "$PSUTIL_SO" 2>/dev/null | grep -q "arm64.*x86_64\|x86_64.*arm64"; then
        echo "   -> fat (universal2): psutil можно оставить в сборке (убрать из excludes в Dублёр_universal2.spec)."
    else
        echo "   -> thin: в Dублёр_universal2.spec psutil должен быть в excludes."
    fi
else
    echo "3. psutil: модуль не найден в .venv_universal2"
fi
echo ""
echo "Готово. По результатам решите, оставлять ли psutil в excludes в Dублёр_universal2.spec."
