#!/bin/bash
set -euo pipefail

APP_NAME="Dублёр.app"
APP_IN_APPLICATIONS="/Applications/$APP_NAME"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NEAR_SCRIPT="$SCRIPT_DIR/$APP_NAME"

show_alert() {
  local title="$1"
  local message="$2"
  osascript -e "display alert \"$title\" message \"$message\" as warning"
}

read_version() {
  /usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$1/Contents/Info.plist" 2>/dev/null || echo "неизвестно"
}

if [ ! -d "$APP_IN_APPLICATIONS" ]; then
  show_alert "Dублёр.app не найден" "Сначала перетащите приложение в папку Программы, затем запустите скрипт повторно."
  exit 1
fi

if [ -d "$APP_NEAR_SCRIPT" ]; then
  DMG_VERSION="$(read_version "$APP_NEAR_SCRIPT")"
  INSTALLED_VERSION="$(read_version "$APP_IN_APPLICATIONS")"
  if [ "$DMG_VERSION" != "$INSTALLED_VERSION" ]; then
    show_alert "Установлена другая версия" "В папке Программы: $INSTALLED_VERSION. В этом DMG: $DMG_VERSION. Перетащите Dублёр.app в Программы и выберите «Заменить». Старая версия не была запущена."
    exit 1
  fi
fi

APP_PATH="$APP_IN_APPLICATIONS"

if ! xattr -dr com.apple.quarantine "$APP_PATH" 2>/dev/null; then
  show_alert "Не удалось снять блокировку" "Проверьте права доступа к приложению и запустите скрипт снова."
  exit 1
fi

open "$APP_PATH"
