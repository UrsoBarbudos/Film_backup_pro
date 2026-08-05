"""
Модуль для работы с настройками приложения Dублёр
"""

import os
import json
import sys


class Config:
    """Класс для управления настройками приложения"""
    
    def __init__(self, settings_file=None):
        """
        Инициализация конфигурации
        
        :param settings_file: Путь к файлу настроек. Если None, используется стандартный путь
        """
        # Legacy путь (для миграции): старый файл в home.
        home_dir = os.path.expanduser("~")
        self.legacy_settings_file = os.path.join(home_dir, ".film_backup_pro_settings.json")

        if settings_file is None:
            # Новый путь: app data dir по правилам платформы.
            # Это повышает переносимость и уменьшает проблемы с правами/песочницами.
            from paths import get_app_data_dir

            app_data_dir = get_app_data_dir()
            os.makedirs(app_data_dir, exist_ok=True)
            self.settings_file = os.path.join(app_data_dir, "settings.json")
        else:
            self.settings_file = settings_file

        # Дополнительная проверка: убеждаемся, что файл не в директории проекта
        # (важно для сборок, чтобы не писать рядом с исходниками).
        project_dir = os.path.abspath(os.path.dirname(__file__))
        try:
            if os.path.commonpath([self.settings_file, project_dir]) == project_dir:
                # Если файл оказался в директории проекта, перемещаем в app data dir.
                from paths import get_app_data_dir

                app_data_dir = get_app_data_dir()
                os.makedirs(app_data_dir, exist_ok=True)
                self.settings_file = os.path.join(app_data_dir, "settings.json")
        except Exception:
            # Если commonpath падает из-за разных корней/форматов — игнорируем.
            pass

    def _get_effective_settings_file_for_read(self) -> str:
        """
        Выбирает файл для чтения с учетом миграции:
        - если новый файл существует — читаем его
        - иначе, если существует legacy файл — читаем legacy
        - иначе вернем новый путь (как источник правды для save)
        """
        if os.path.exists(self.settings_file):
            return self.settings_file
        if os.path.exists(getattr(self, "legacy_settings_file", "")):
            return self.legacy_settings_file
        return self.settings_file
    
    def _get_default_settings(self):
        """Возвращает настройки по умолчанию"""
        return {
            'prevent_sleep': True,
            'theme': 'light',
            'create_md_log': False,
            'verification_mode': 'full',
            'last_source_dir': None,
            'last_destination_dir': None,
            'telegram_enabled': False,
            'telegram_bot_token': None,
            'telegram_chat_id': None,
            'macos_notifications_enabled': True,
            'hash_storage_use_compression': True,
            'mark_source_after_verified_backup': True,
            'warn_on_previously_backed_up_source': True,
        }
    
    def load(self):
        """
        Загружает настройки из файла
        
        :return: Словарь с настройками
        """
        default_settings = self._get_default_settings()
        
        try:
            settings_path = self._get_effective_settings_file_for_read()
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    
                    settings = {**default_settings, **loaded_settings}
                    
                    # ВАЖНО: При сборке приложения (frozen) очищаем данные Telegram
                    # только один раз при первой загрузке, если файл настроек содержит данные Telegram
                    # (т.е. это данные разработчика, которые нужно очистить)
                    # После сохранения пользователем, данные должны оставаться
                    if getattr(sys, 'frozen', False):
                        # Проверяем флаг, который указывает, что данные Telegram были сохранены пользователем
                        # Если флаг установлен - не очищаем данные
                        telegram_user_saved = loaded_settings.get('_telegram_user_saved', False)
                        
                        if not telegram_user_saved:
                            # Проверяем, есть ли данные Telegram в загруженных настройках
                            # Если есть - это данные разработчика, их нужно очистить один раз
                            has_telegram_data = (
                                loaded_settings.get('telegram_bot_token') is not None or
                                loaded_settings.get('telegram_chat_id') is not None
                            )
                            
                            if has_telegram_data:
                                # Очищаем данные Telegram только если они были в файле (данные разработчика)
                                # и они еще не были сохранены пользователем
                                settings['telegram_enabled'] = False
                                settings['telegram_bot_token'] = None
                                settings['telegram_chat_id'] = None
                    
                    # Проверяем, что пути существуют
                    if settings.get('last_source_dir') and not os.path.exists(settings['last_source_dir']):
                        settings['last_source_dir'] = None
                    if settings.get('last_destination_dir') and not os.path.exists(settings['last_destination_dir']):
                        settings['last_destination_dir'] = None
                    
                    return settings
        except Exception as e:
            print(f"WARNING: Не удалось загрузить настройки: {e}", flush=True)
        
        return default_settings
    
    def _load_raw_settings(self):
        """
        Загружает настройки напрямую из файла без очистки данных Telegram.
        Используется в методе save() чтобы не очищать данные, которые пользователь только что ввел.
        
        :return: Словарь с настройками из файла или значения по умолчанию
        """
        default_settings = self._get_default_settings()
        
        try:
            settings_path = self._get_effective_settings_file_for_read()
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    settings = {**default_settings, **loaded_settings}
                    
                    # Проверяем, что пути существуют
                    if settings.get('last_source_dir') and not os.path.exists(settings['last_source_dir']):
                        settings['last_source_dir'] = None
                    if settings.get('last_destination_dir') and not os.path.exists(settings['last_destination_dir']):
                        settings['last_destination_dir'] = None
                    
                    return settings
        except Exception as e:
            print(f"WARNING: Не удалось загрузить настройки: {e}", flush=True)
        
        return default_settings
    
    def save(self, **settings):
        """
        Сохраняет настройки в файл
        
        :param settings: Настройки для сохранения (ключевые аргументы)
        """
        try:
            # Загружаем существующие настройки напрямую из файла без очистки Telegram
            # Это позволяет сохранить данные Telegram, которые пользователь только что ввел
            current_settings = self._load_raw_settings()
            # Обновляем их новыми значениями
            current_settings.update(settings)
            
            # Если пользователь сохраняет данные Telegram, устанавливаем флаг
            # чтобы при следующей загрузке они не очищались
            if getattr(sys, 'frozen', False):
                if 'telegram_bot_token' in settings or 'telegram_chat_id' in settings:
                    # Проверяем, что пользователь действительно ввел данные (не None и не пустые строки)
                    telegram_token = settings.get('telegram_bot_token', current_settings.get('telegram_bot_token'))
                    telegram_chat_id = settings.get('telegram_chat_id', current_settings.get('telegram_chat_id'))
                    
                    # Устанавливаем флаг только если есть хотя бы одно непустое значение
                    if (telegram_token is not None and str(telegram_token).strip()) or \
                       (telegram_chat_id is not None and str(telegram_chat_id).strip()):
                        # Устанавливаем флаг, что данные Telegram были сохранены пользователем
                        current_settings['_telegram_user_saved'] = True
            
            # Атомарная запись: пишем во временный файл рядом, затем заменяем.
            target_path = self.settings_file
            target_dir = os.path.dirname(target_path) or "."
            os.makedirs(target_dir, exist_ok=True)

            tmp_path = target_path + ".tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(current_settings, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, target_path)
            finally:
                # Если replace упал, не оставляем мусорный tmp.
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
        except Exception as e:
            print(f"WARNING: Не удалось сохранить настройки: {e}", flush=True)
    
    def get(self, key, default=None):
        """
        Получает значение настройки
        
        :param key: Ключ настройки
        :param default: Значение по умолчанию, если настройка не найдена
        :return: Значение настройки или default
        """
        settings = self.load()
        return settings.get(key, default)
    
    def set(self, key, value):
        """
        Устанавливает значение настройки
        
        :param key: Ключ настройки
        :param value: Значение настройки
        """
        self.save(**{key: value})
