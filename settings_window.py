"""
Окно настроек приложения Dублёр (PySide6 версия)
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QFrame, QLineEdit, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QMouseEvent
from typing import Callable, Optional

from widgets import PyToggle
from ui.ui_constants import UISpacing, UISizes


def _toggle_colors_for_theme(theme: str):
    """Цвета трека и кружка PyToggle для светлой/тёмной темы."""
    if theme == "dark":
        return {"bg_color": "#555", "circle_color": "#eee", "active_color": "#4A90E2"}
    return {"bg_color": "#ccc", "circle_color": "#333", "active_color": "#4A90E2"}


class ClickableThemeLabel(QLabel):
    """Кликабельный QLabel для переключения темы"""
    
    def __init__(self, text, callback=None, parent=None):
        super().__init__(text, parent)
        self.callback = callback
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("ThemeValueLabel")
    
    def mousePressEvent(self, event: QMouseEvent):
        """Обработка клика по метке"""
        if event.button() == Qt.MouseButton.LeftButton and self.callback:
            self.callback()
        super().mousePressEvent(event)


class SettingsPage(QWidget):
    """Страница настроек приложения (встраивается в главное окно)."""
    
    def __init__(self, parent, app_instance, on_close: Optional[Callable[[], None]] = None):
        """
        Инициализация модального окна настроек
        
        :param parent: Родительское окно
        :param app_instance: Экземпляр главного приложения для доступа к настройкам
        """
        try:
            super().__init__(parent)
            
            self.app = app_instance
            self.on_close = on_close
            self.telegram_client = self.app.telegram_client
            
            # Настройки уведомлений
            settings = self.app.config.load()
            
            # Переменные для хранения значений настроек
            self.prevent_sleep_var = self.app.prevent_sleep
            self.theme_var = self.app.theme
            self.initial_theme_var = self.app.theme  # Сохраняем исходное значение для восстановления при отмене
            self.create_md_log_var = self.app.create_md_log
            self.verification_mode_var = settings.get('verification_mode', 'full')
            self.macos_notifications_enabled_var = settings.get('macos_notifications_enabled', True)
            self.telegram_enabled_var = settings.get('telegram_enabled', False)
            self.telegram_bot_token_var = settings.get('telegram_bot_token', None) or ''
            self.telegram_chat_id_var = settings.get('telegram_chat_id', None) or ''
            self.mark_source_after_verified_backup_var = settings.get(
                'mark_source_after_verified_backup', True
            )
            self.warn_on_previously_backed_up_source_var = settings.get(
                'warn_on_previously_backed_up_source', True
            )
            
            # Создаем интерфейс
            self._create_widgets()
            
            # Применяем тему
            self._apply_theme()
        except Exception as e:
            import traceback
            print(f"ERROR: Failed to initialize SettingsPage: {e}", flush=True)
            traceback.print_exc()
            raise

    def refresh_from_app_state(self):
        """Обновляет значения страницы из текущего состояния приложения перед показом."""
        settings = self.app.config.load()
        self.prevent_sleep_var = self.app.prevent_sleep
        self.theme_var = self.app.theme
        self.initial_theme_var = self.app.theme
        self.create_md_log_var = self.app.create_md_log
        self.verification_mode_var = settings.get('verification_mode', 'full')
        self.macos_notifications_enabled_var = settings.get('macos_notifications_enabled', True)
        self.telegram_enabled_var = settings.get('telegram_enabled', False)
        self.telegram_bot_token_var = settings.get('telegram_bot_token', None) or ''
        self.telegram_chat_id_var = settings.get('telegram_chat_id', None) or ''
        self.mark_source_after_verified_backup_var = settings.get(
            'mark_source_after_verified_backup', True
        )
        self.warn_on_previously_backed_up_source_var = settings.get(
            'warn_on_previously_backed_up_source', True
        )

        self.prevent_sleep_checkbox.setChecked(self.prevent_sleep_var)
        self.theme_value_label.setText(self.theme_var)
        verification_mode_display = "Полная" if self.verification_mode_var == 'full' else "Быстрая"
        self.verification_mode_value_label.setText(verification_mode_display)
        self.mdlog_checkbox.setChecked(self.create_md_log_var)
        self.macos_notifications_checkbox.setChecked(self.macos_notifications_enabled_var)
        self.telegram_enabled_checkbox.setChecked(self.telegram_enabled_var)
        self.telegram_token_input.setText(self.telegram_bot_token_var)
        self.telegram_chat_id_input.setText(self.telegram_chat_id_var)
        self.mark_source_checkbox.setChecked(self.mark_source_after_verified_backup_var)
        self.warn_previous_backup_checkbox.setChecked(
            self.warn_on_previously_backed_up_source_var
        )
        self._on_telegram_enabled_toggled(self.telegram_enabled_var)
        self._apply_theme()
    
    def _create_widgets(self):
        """Создает все виджеты окна настроек"""
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 16, 0, 0)
        main_layout.setSpacing(0)

        content_container = QWidget(self)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(16, 0, 16, 0)
        content_layout.setSpacing(0)
        
        # Scrollable area: место под скроллбар всегда зарезервировано (нет сдвига при вкл/выкл Telegram),
        # визуально скроллбар скрыт, когда прокрутка не нужна
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll_area.setStyleSheet("border: none;")
        self._settings_scroll_area = scroll_area

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(8, 8, 8, 8)
        scroll_layout.setSpacing(12)
        
        # Секция "Копирование"
        copy_section_label = QLabel("Копирование")
        copy_section_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        copy_section_label.setObjectName("SectionHeader")
        scroll_layout.addWidget(copy_section_label)
        scroll_layout.addSpacing(-6)  # Приближаем заголовок к содержимому
        
        prevent_sleep_frame = QFrame()
        prevent_sleep_layout = QVBoxLayout(prevent_sleep_frame)
        prevent_sleep_layout.setContentsMargins(0, 4, 0, 4)
        prevent_sleep_layout.setSpacing(8)
        
        self.prevent_sleep_checkbox = PyToggle(
            "Предотвращать спящий режим во время копирования",
            **_toggle_colors_for_theme(self.app.theme),
        )
        self.prevent_sleep_checkbox.setChecked(self.prevent_sleep_var)
        self.prevent_sleep_checkbox.setFont(QFont("Arial", 13))
        prevent_sleep_layout.addWidget(self.prevent_sleep_checkbox)
        
        prevent_sleep_desc = QLabel("Не даёт Mac засыпать во время копирования")
        prevent_sleep_desc.setObjectName("DescriptionLabel")
        prevent_sleep_desc.setWordWrap(True)
        prevent_sleep_desc.setContentsMargins(20, 0, 0, 0)  # Отступ для выравнивания с текстом чекбокса
        prevent_sleep_desc.setFont(QFont("Arial", 12))
        prevent_sleep_layout.addWidget(prevent_sleep_desc)
        
        scroll_layout.addWidget(prevent_sleep_frame)
        
        # Режим проверки файлов
        verification_mode_frame = QFrame()
        verification_mode_layout = QHBoxLayout(verification_mode_frame)
        
        verification_mode_label = QLabel("Режим проверки файлов:")
        verification_mode_label.setFont(QFont("Arial", 13))
        verification_mode_label.setObjectName("ThemeLabel")
        verification_mode_layout.addWidget(verification_mode_label)
        
        # Преобразуем значение для отображения
        verification_mode_display = "Полная" if self.verification_mode_var == 'full' else "Быстрая"
        self.verification_mode_value_label = ClickableThemeLabel(
            verification_mode_display,
            callback=self._on_verification_mode_change
        )
        self.verification_mode_value_label.setFont(QFont("Arial", 13))
        self.verification_mode_value_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.verification_mode_value_label.setObjectName("VerificationModeValueLabel")
        verification_mode_layout.addWidget(self.verification_mode_value_label)
        verification_mode_layout.addStretch()
        
        scroll_layout.addWidget(verification_mode_frame)
        
        # Описание режимов проверки
        verification_mode_desc = QLabel("Быстрая — по размеру файла. Полная — по MD5 и с поиском дубликатов.")
        verification_mode_desc.setObjectName("DescriptionLabel")
        verification_mode_desc.setWordWrap(True)
        verification_mode_desc.setContentsMargins(20, 0, 0, 0)
        verification_mode_desc.setFont(QFont("Arial", 12))
        scroll_layout.addWidget(verification_mode_desc)
        
        # Создание MD лога
        mdlog_frame = QFrame()
        mdlog_layout = QVBoxLayout(mdlog_frame)
        mdlog_layout.setContentsMargins(0, 4, 0, 4)
        mdlog_layout.setSpacing(8)
        
        self.mdlog_checkbox = PyToggle(
            "Создавать MD файл с логом сессии",
            **_toggle_colors_for_theme(self.app.theme),
        )
        self.mdlog_checkbox.setChecked(self.create_md_log_var)
        self.mdlog_checkbox.setFont(QFont("Arial", 13))
        mdlog_layout.addWidget(self.mdlog_checkbox)
        
        mdlog_desc = QLabel("Файл с отчётом (статистика, список файлов) в папке назначения")
        mdlog_desc.setObjectName("DescriptionLabel")
        mdlog_desc.setWordWrap(True)
        mdlog_desc.setContentsMargins(20, 0, 0, 0)  # Отступ для выравнивания с текстом чекбокса
        mdlog_desc.setFont(QFont("Arial", 12))
        mdlog_layout.addWidget(mdlog_desc)
        
        scroll_layout.addWidget(mdlog_frame)

        marker_section_label = QLabel("Отметка на исходном носителе")
        marker_section_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        marker_section_label.setObjectName("SectionHeader")
        scroll_layout.addWidget(marker_section_label)
        scroll_layout.addSpacing(-6)

        marker_frame = QFrame()
        marker_layout = QVBoxLayout(marker_frame)
        marker_layout.setContentsMargins(0, 4, 0, 4)
        marker_layout.setSpacing(8)
        self.mark_source_checkbox = PyToggle(
            "Отмечать успешно скопированные носители",
            **_toggle_colors_for_theme(self.app.theme),
        )
        self.mark_source_checkbox.setChecked(self.mark_source_after_verified_backup_var)
        self.mark_source_checkbox.setFont(QFont("Arial", 13))
        marker_layout.addWidget(self.mark_source_checkbox)
        marker_desc = QLabel(
            "После успешного копирования и проверки Дублёр сохранит "
            "на исходном носителе скрытую служебную отметку. "
            "Исходные медиаданные не изменяются."
        )
        marker_desc.setObjectName("DescriptionLabel")
        marker_desc.setWordWrap(True)
        marker_desc.setContentsMargins(20, 0, 0, 0)
        marker_desc.setFont(QFont("Arial", 12))
        marker_layout.addWidget(marker_desc)
        scroll_layout.addWidget(marker_frame)

        warning_frame = QFrame()
        warning_layout = QVBoxLayout(warning_frame)
        warning_layout.setContentsMargins(0, 4, 0, 4)
        warning_layout.setSpacing(8)
        self.warn_previous_backup_checkbox = PyToggle(
            "Предупреждать о ранее скопированных носителях",
            **_toggle_colors_for_theme(self.app.theme),
        )
        self.warn_previous_backup_checkbox.setChecked(
            self.warn_on_previously_backed_up_source_var
        )
        self.warn_previous_backup_checkbox.setFont(QFont("Arial", 13))
        warning_layout.addWidget(self.warn_previous_backup_checkbox)
        warning_desc = QLabel(
            "При добавлении отмеченного носителя Дублёр предложит отменить "
            "или явно разрешить повторное копирование."
        )
        warning_desc.setObjectName("DescriptionLabel")
        warning_desc.setWordWrap(True)
        warning_desc.setContentsMargins(20, 0, 0, 0)
        warning_desc.setFont(QFont("Arial", 12))
        warning_layout.addWidget(warning_desc)
        scroll_layout.addWidget(warning_frame)
        
        # Секция "Внешний вид"
        appearance_label = QLabel("Внешний вид")
        appearance_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        appearance_label.setObjectName("SectionHeader")
        scroll_layout.addWidget(appearance_label)
        scroll_layout.addSpacing(-6)  # Приближаем заголовок к содержимому
        
        theme_frame = QFrame()
        theme_layout = QHBoxLayout(theme_frame)
        
        theme_label = QLabel("Тема оформления:")
        theme_label.setFont(QFont("Arial", 13))
        theme_label.setObjectName("ThemeLabel")
        theme_layout.addWidget(theme_label)
        
        self.theme_value_label = ClickableThemeLabel(self.theme_var, callback=self._on_theme_change)
        self.theme_value_label.setFont(QFont("Arial", 13))
        # Ограничиваем размер виджета размером содержимого, чтобы кликабельная область соответствовала тексту
        self.theme_value_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        theme_layout.addWidget(self.theme_value_label)
        theme_layout.addStretch()
        
        scroll_layout.addWidget(theme_frame)
        
        # Секция "Уведомления"
        notifications_label = QLabel("Уведомления")
        notifications_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        notifications_label.setObjectName("SectionHeader")
        scroll_layout.addWidget(notifications_label)
        scroll_layout.addSpacing(-6)  # Приближаем заголовок к содержимому
        
        # Системные уведомления macOS
        macos_notifications_frame = QFrame()
        macos_notifications_layout = QVBoxLayout(macos_notifications_frame)
        macos_notifications_layout.setContentsMargins(0, 4, 0, 4)
        macos_notifications_layout.setSpacing(8)
        
        self.macos_notifications_checkbox = PyToggle(
            "Включить системные уведомления macOS",
            **_toggle_colors_for_theme(self.app.theme),
        )
        self.macos_notifications_checkbox.setChecked(self.macos_notifications_enabled_var)
        self.macos_notifications_checkbox.setFont(QFont("Arial", 13))
        macos_notifications_layout.addWidget(self.macos_notifications_checkbox)
        
        macos_notifications_desc = QLabel("Уведомление в Notification Center по завершении")
        macos_notifications_desc.setObjectName("DescriptionLabel")
        macos_notifications_desc.setWordWrap(True)
        macos_notifications_desc.setContentsMargins(20, 0, 0, 0)
        macos_notifications_desc.setFont(QFont("Arial", 12))
        macos_notifications_layout.addWidget(macos_notifications_desc)
        
        scroll_layout.addWidget(macos_notifications_frame)
        
        # Telegram уведомления
        telegram_frame = QFrame()
        telegram_layout = QVBoxLayout(telegram_frame)
        telegram_layout.setContentsMargins(0, 4, 0, 4)
        telegram_layout.setSpacing(8)
        
        self.telegram_enabled_checkbox = PyToggle(
            "Включить уведомления Telegram",
            **_toggle_colors_for_theme(self.app.theme),
        )
        self.telegram_enabled_checkbox.setChecked(self.telegram_enabled_var)
        self.telegram_enabled_checkbox.setFont(QFont("Arial", 13))
        self.telegram_enabled_checkbox.toggled.connect(self._on_telegram_enabled_toggled)
        telegram_layout.addWidget(self.telegram_enabled_checkbox)
        
        telegram_desc = QLabel("Отправка лога в Telegram. Нужны Bot Token и Chat ID.")
        telegram_desc.setObjectName("DescriptionLabel")
        telegram_desc.setWordWrap(True)
        telegram_desc.setContentsMargins(20, 0, 0, 0)   
        telegram_desc.setFont(QFont("Arial", 12))
        telegram_layout.addWidget(telegram_desc)
        
        # Контейнер для полей ввода Telegram (показывается только при включенном чекбоксе)
        self.telegram_fields_container = QWidget()
        telegram_fields_layout = QVBoxLayout(self.telegram_fields_container)
        telegram_fields_layout.setContentsMargins(20, 4, 0, 12)
        telegram_fields_layout.setSpacing(8)
        
        # Telegram Bot Token - в одну строку
        token_row_layout = QHBoxLayout()
        token_row_layout.setSpacing(8)
        token_label = QLabel("Telegram Bot Token:")
        token_label.setFont(QFont("Arial", 12))
        token_label.setMinimumWidth(130)
        token_row_layout.addWidget(token_label)
        
        self.telegram_token_input = QLineEdit()
        self.telegram_token_input.setPlaceholderText("Токен от @BotFather")
        self.telegram_token_input.setText(self.telegram_bot_token_var)
        self.telegram_token_input.setEchoMode(QLineEdit.EchoMode.Password)  # Маскирование для безопасности
        self.telegram_token_input.setFont(QFont("Arial", 12))
        self.telegram_token_input.setFixedHeight(28)
        self.telegram_token_input.setFixedWidth(250)  # Фиксированная ширина поля ввода
        self.telegram_token_input.setObjectName("ApiKeyInput")
        self.telegram_token_input.editingFinished.connect(self._on_token_input_finished)
        token_row_layout.addWidget(self.telegram_token_input)
        token_row_layout.addStretch()  # Растягиваем оставшееся пространство, чтобы поле не расширялось
        
        telegram_fields_layout.addLayout(token_row_layout)
        
        token_help = QLabel("@BotFather → /newbot")
        token_help.setObjectName("DescriptionLabel")
        token_help.setWordWrap(True)
        token_help.setContentsMargins(0, 0, 0, 0)
        token_help.setFont(QFont("Arial", 12))
        telegram_fields_layout.addWidget(token_help)
        
        # Telegram Chat ID - в одну строку
        chat_id_row_layout = QHBoxLayout()
        chat_id_row_layout.setSpacing(8)
        chat_id_label = QLabel("Telegram Chat ID:")
        chat_id_label.setFont(QFont("Arial", 12))
        chat_id_label.setMinimumWidth(130)
        chat_id_row_layout.addWidget(chat_id_label)
        
        self.telegram_chat_id_input = QLineEdit()
        self.telegram_chat_id_input.setPlaceholderText("Chat ID")
        self.telegram_chat_id_input.setText(self.telegram_chat_id_var)
        self.telegram_chat_id_input.setFont(QFont("Arial", 12))
        self.telegram_chat_id_input.setFixedHeight(28)
        self.telegram_chat_id_input.setFixedWidth(250)  # Фиксированная ширина поля ввода
        self.telegram_chat_id_input.setObjectName("ApiKeyInput")
        self.telegram_chat_id_input.editingFinished.connect(self._on_chat_id_input_finished)
        chat_id_row_layout.addWidget(self.telegram_chat_id_input)
        chat_id_row_layout.addStretch()  # Растягиваем оставшееся пространство, чтобы поле не расширялось
        
        telegram_fields_layout.addLayout(chat_id_row_layout)
        
        chat_id_help = QLabel("@userinfobot")
        chat_id_help.setObjectName("DescriptionLabel")
        chat_id_help.setWordWrap(True)
        chat_id_help.setContentsMargins(0, 0, 0, 0)
        chat_id_help.setFont(QFont("Arial", 12))
        telegram_fields_layout.addWidget(chat_id_help)
        
        telegram_layout.addWidget(self.telegram_fields_container)
        
        scroll_layout.addWidget(telegram_frame)
        
        # Обновляем видимость полей Telegram при инициализации
        self._on_telegram_enabled_toggled(self.telegram_enabled_var)
        
        # Инициализируем начальное состояние полей ввода (серая рамка для пустых полей)
        # Это будет применено после _apply_theme()
        
        # Секция "О программе"
        about_label = QLabel("О программе")
        about_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        about_label.setObjectName("SectionHeader")
        scroll_layout.addWidget(about_label)
        scroll_layout.addSpacing(-6)  # Приближаем заголовок к содержимому
        
        about_frame = QFrame()
        about_layout = QVBoxLayout(about_frame)
        about_layout.setContentsMargins(0, 4, 0, 4)
        about_layout.setSpacing(8)
        
        version_label = QLabel(f"Версия: {self.app.APP_VERSION}")
        version_label.setFont(QFont("Arial", 13))
        version_label.setObjectName("AboutLabel")
        about_layout.addWidget(version_label)
        
        author_label = QLabel(f"Автор: {self.app.APP_AUTHOR}")
        author_label.setFont(QFont("Arial", 13))
        author_label.setObjectName("AboutLabel")
        about_layout.addWidget(author_label)
        
        scroll_layout.addWidget(about_frame)
        
        scroll_layout.addStretch()
        
        scroll_area.setWidget(scroll_widget)
        content_layout.addWidget(scroll_area)
        main_layout.addWidget(content_container)

        vbar = scroll_area.verticalScrollBar()
        vbar.rangeChanged.connect(self._on_settings_scroll_range_changed)
        self._on_settings_scroll_range_changed(vbar.minimum(), vbar.maximum())

        # Кнопки управления
        buttons_layout = QHBoxLayout()
        # Горизонтальные inset не добавляем: ширина ряда должна совпадать
        # с рядом кнопки "Начать копирование" в главном окне.
        buttons_layout.setContentsMargins(0, UISpacing.BUTTONS, 0, 0)
        buttons_layout.setSpacing(UISpacing.INTERNAL)
        
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setFixedHeight(UISizes.BUTTON_HEIGHT)
        self.cancel_button.clicked.connect(self._on_cancel)
        buttons_layout.addWidget(self.cancel_button, 1)
        
        self.ok_button = QPushButton("OK")
        self.ok_button.setFixedHeight(UISizes.BUTTON_HEIGHT)
        self.ok_button.clicked.connect(self._on_ok)
        buttons_layout.addWidget(self.ok_button, 1)
        
        main_layout.addLayout(buttons_layout)
    
    def _on_settings_scroll_range_changed(self, _min: int, _max: int) -> None:
        """Скрывает вертикальный скроллбар визуально, когда прокрутка не нужна (место под него зарезервировано)."""
        if not hasattr(self, "_settings_scroll_area"):
            return
        vbar = self._settings_scroll_area.verticalScrollBar()
        no_scroll_needed = _max <= _min
        bg = "#2b2b2b" if self.app.theme == "dark" else "white"
        if no_scroll_needed:
            vbar.setStyleSheet(
                f"QScrollBar:vertical {{ background: {bg}; width: 14px; border: none; border-radius: 7px; margin: 0; }}"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { height: 0; }"
                "QScrollBar::handle:vertical { min-height: 0; background: transparent; }"
            )
        else:
            if self.app.theme == "dark":
                vbar.setStyleSheet(
                    "QScrollBar:vertical { background: #3a3a3a; width: 14px; border: none; border-radius: 7px; margin: 0; }"
                    "QScrollBar::handle:vertical { min-height: 20px; background: #666; border-radius: 7px; }"
                    "QScrollBar::handle:vertical:hover { background: #777; }"
                    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
                )
            else:
                vbar.setStyleSheet(
                    "QScrollBar:vertical { background: #e0e0e0; width: 14px; border: none; border-radius: 7px; margin: 0; }"
                    "QScrollBar::handle:vertical { min-height: 20px; background: #b0b0b0; border-radius: 7px; }"
                    "QScrollBar::handle:vertical:hover { background: #999; }"
                    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
                )

    def _apply_theme(self):
        """Применяет тему оформления к окну настроек"""
        if self.app.theme == 'dark':
            self.setStyleSheet("""
                QDialog {
                    background-color: #2b2b2b;
                    color: white;
                }
                QWidget {
                    background-color: #2b2b2b;
                    color: white;
                }
                QLabel#SectionHeader {
                    color: white;
                    font-weight: bold;
                }
                QLabel#ThemeLabel {
                    color: white;
                }
                QLabel#ThemeValueLabel {
                    color: white;
                    text-decoration: underline;
                }
                QLabel#VerificationModeValueLabel {
                    color: white;
                    text-decoration: underline;
                }
                QLabel#DescriptionLabel {
                    color: #aaa;
                }
                QLabel#AboutLabel {
                    color: #aaa;
                }
                QCheckBox {
                    color: white;
                }
                QCheckBox:disabled {
                    color: #888;
                }
                QPushButton {
                    background-color: #555;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px;
                }
                QPushButton:hover {
                    background-color: #666;
                }
                QScrollArea {
                    background-color: #2b2b2b;
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: #2b2b2b;
                }
                QLineEdit#ApiKeyInput {
                    background-color: #3a3a3a;
                    border: 2px solid #808080;
                    border-radius: 4px;
                    padding: 3px 6px;
                    color: white;
                }
                QLineEdit#ApiKeyInput:focus {
                    border: 2px solid #999999;
                    background-color: #404040;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: white;
                    color: black;
                }
                QWidget {
                    background-color: white;
                    color: black;
                }
                QLabel#SectionHeader {
                    color: black;
                    font-weight: bold;
                }
                QLabel#ThemeLabel {
                    color: black;
                }
                QLabel#ThemeValueLabel {
                    color: black;
                    text-decoration: underline;
                }
                QLabel#VerificationModeValueLabel {
                    color: black;
                    text-decoration: underline;
                }
                QLabel#DescriptionLabel {
                    color: #666;
                }
                QLabel#AboutLabel {
                    color: #666;
                }
                QCheckBox {
                    color: black;
                }
                QCheckBox:disabled {
                    color: #888;
                }
                QPushButton {
                    background-color: #999;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px;
                }
                QPushButton:hover {
                    background-color: #888;
                }
                QScrollArea {
                    background-color: white;
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: white;
                }
                QLineEdit#ApiKeyInput {
                    background-color: #f5f5f5;
                    border: 2px solid #808080;
                    border-radius: 4px;
                    padding: 3px 6px;
                    color: black;
                }
                QLineEdit#ApiKeyInput:focus {
                    border: 2px solid #999999;
                    background-color: #ffffff;
                }
            """)
        
        # Обновляем цвета трека PyToggle при смене темы
        toggles = [
            self.prevent_sleep_checkbox,
            self.mdlog_checkbox,
            self.mark_source_checkbox,
            self.warn_previous_backup_checkbox,
            self.macos_notifications_checkbox,
            self.telegram_enabled_checkbox,
        ]
        colors = _toggle_colors_for_theme(self.app.theme)
        for t in toggles:
            t.set_toggle_colors(
                colors["bg_color"],
                colors["circle_color"],
                colors["active_color"],
            )

        # Инициализируем состояние полей ввода API (применяется через _set_api_input_style)
        self._initialize_api_inputs_state()
        # Обновляем вид скроллбара (цвет фона при «нет прокрутки» зависит от темы)
        if hasattr(self, "_settings_scroll_area"):
            vbar = self._settings_scroll_area.verticalScrollBar()
            self._on_settings_scroll_range_changed(vbar.minimum(), vbar.maximum())

    def _on_theme_change(self):
        """Обработчик изменения темы (применяется сразу)"""
        # Переключаем тему между light и dark
        self.theme_var = "dark" if self.theme_var == "light" else "light"
        # Обновляем текст в label
        self.theme_value_label.setText(self.theme_var)
        # Применяем тему к главному окну
        self.app.theme = self.theme_var
        self.app._apply_theme()
        # Применяем тему к окну настроек
        self._apply_theme()
    
    def _on_verification_mode_change(self):
        """Обработчик изменения режима проверки файлов"""
        # Переключаем режим между full и fast
        self.verification_mode_var = "fast" if self.verification_mode_var == "full" else "full"
        # Обновляем текст в label
        verification_mode_display = "Полная" if self.verification_mode_var == 'full' else "Быстрая"
        self.verification_mode_value_label.setText(verification_mode_display)
    
    def _apply_settings(self):
        """Применяет настройки к приложению"""
        self.app.prevent_sleep = self.prevent_sleep_checkbox.isChecked()
        self.app.theme = self.theme_var
        self.app.create_md_log = self.mdlog_checkbox.isChecked()
        self.app.verification_mode = self.verification_mode_var
        
        # Настройки уведомлений
        macos_notifications_enabled = self.macos_notifications_checkbox.isChecked()
        telegram_enabled = self.telegram_enabled_checkbox.isChecked()
        telegram_bot_token = self.telegram_token_input.text().strip() or None
        telegram_chat_id = self.telegram_chat_id_input.text().strip() or None
        
        # Применяем тему к главному окну
        self.app._apply_theme()
        # Применяем тему к окну настроек
        self._apply_theme()
        
        # Сохраняем настройки
        self.app.config.save(
            prevent_sleep=self.app.prevent_sleep,
            theme=self.app.theme,
            create_md_log=self.app.create_md_log,
            verification_mode=self.app.verification_mode,
            macos_notifications_enabled=macos_notifications_enabled,
            telegram_enabled=telegram_enabled,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
            mark_source_after_verified_backup=self.mark_source_checkbox.isChecked(),
            warn_on_previously_backed_up_source=self.warn_previous_backup_checkbox.isChecked(),
        )
    
    def _on_ok(self):
        """Обработчик кнопки 'OK'"""
        self._apply_settings()
        if self.on_close:
            self.on_close()
    
    def _on_telegram_enabled_toggled(self, enabled: bool):
        """Обработчик переключения чекбокса включения Telegram уведомлений"""
        # Показываем/скрываем поля ввода в зависимости от состояния чекбокса
        self.telegram_fields_container.setVisible(enabled)
        self.telegram_token_input.setEnabled(enabled)
        self.telegram_chat_id_input.setEnabled(enabled)
    
    def _validate_telegram_token(self, token: str) -> tuple[bool, str | None]:
        """Проверяет токен через единый Telegram-клиент."""
        if not token or not token.strip():
            return False, None

        result = self.telegram_client.validate_token(token.strip())
        return result.success, None if result.success else result.message
    
    def _validate_telegram_chat_id(self, chat_id: str, token: str | None = None) -> tuple[bool, str | None]:
        """Проверяет Chat ID локально и, при наличии токена, тестовым сообщением."""
        if not chat_id or not chat_id.strip():
            return False, None

        chat_id = chat_id.strip()
        format_result = self.telegram_client.validate_chat_id_format(chat_id)
        if not format_result.success:
            return False, format_result.message
        if not token:
            return True, None

        result = self.telegram_client.send_message(
            token,
            chat_id,
            "Тестовое сообщение от Dублёр",
        )
        return result.success, None if result.success else result.message
    
    def _set_api_input_style(self, input_field, state: str):
        """
        Устанавливает стиль для поля ввода API в зависимости от состояния
        
        :param input_field: QLineEdit поле ввода
        :param state: Состояние - "empty", "success" или "error"
        """
        if not input_field:
            return
        
        # Определяем стили в зависимости от темы и состояния
        if self.app.theme == 'dark':
            if state == "empty":
                stylesheet = """
                    QLineEdit {
                        background-color: #3a3a3a;
                        border: 2px solid #808080;
                        border-radius: 4px;
                        padding: 3px 6px;
                        color: white;
                    }
                    QLineEdit:focus {
                        border: 2px solid #999999;
                        background-color: #404040;
                    }
                """
            elif state == "success":
                stylesheet = """
                    QLineEdit {
                        background-color: #2d4a2d;
                        border: 2px solid #2FA572;
                        border-radius: 4px;
                        padding: 3px 6px;
                        color: white;
                    }
                    QLineEdit:focus {
                        border: 2px solid #3BC689;
                        background-color: #355a35;
                    }
                """
            else:  # error
                stylesheet = """
                    QLineEdit {
                        background-color: #4a2d2d;
                        border: 2px solid #e87373;
                        border-radius: 4px;
                        padding: 3px 6px;
                        color: white;
                    }
                    QLineEdit:focus {
                        border: 2px solid #ff8a8a;
                        background-color: #5a3535;
                    }
                """
        else:  # light theme
            if state == "empty":
                stylesheet = """
                    QLineEdit {
                        background-color: #f5f5f5;
                        border: 2px solid #808080;
                        border-radius: 4px;
                        padding: 3px 6px;
                        color: black;
                    }
                    QLineEdit:focus {
                        border: 2px solid #999999;
                        background-color: #ffffff;
                    }
                """
            elif state == "success":
                stylesheet = """
                    QLineEdit {
                        background-color: #e8f5e9;
                        border: 2px solid #2FA572;
                        border-radius: 4px;
                        padding: 3px 6px;
                        color: black;
                    }
                    QLineEdit:focus {
                        border: 2px solid #3BC689;
                        background-color: #f1f8f1;
                    }
                """
            else:  # error
                stylesheet = """
                    QLineEdit {
                        background-color: #ffe8e8;
                        border: 2px solid #e87373;
                        border-radius: 4px;
                        padding: 3px 6px;
                        color: black;
                    }
                    QLineEdit:focus {
                        border: 2px solid #ff8a8a;
                        background-color: #fff1f1;
                    }
                """
        
        # Применяем стиль к полю ввода
        input_field.setStyleSheet(stylesheet)
        input_field.style().unpolish(input_field)
        input_field.style().polish(input_field)
        input_field.update()
    
    def _initialize_api_inputs_state(self):
        """Инициализирует начальное состояние полей ввода API"""
        # Устанавливаем серую рамку для пустых полей
        if self.telegram_token_input:
            token = self.telegram_token_input.text().strip()
            if not token:
                self._set_api_input_style(self.telegram_token_input, "empty")
        
        if self.telegram_chat_id_input:
            chat_id = self.telegram_chat_id_input.text().strip()
            if not chat_id:
                self._set_api_input_style(self.telegram_chat_id_input, "empty")
    
    def _on_token_input_finished(self):
        """Обработчик потери фокуса полем токена"""
        token = self.telegram_token_input.text().strip()
        
        if not token:
            # Пустое поле - серая рамка
            self._set_api_input_style(self.telegram_token_input, "empty")
            return
        
        # Валидация токена
        success, error_message = self._validate_telegram_token(token)
        
        if success:
            self._set_api_input_style(self.telegram_token_input, "success")
        else:
            self._set_api_input_style(self.telegram_token_input, "error")
    
    def _on_chat_id_input_finished(self):
        """Обработчик потери фокуса полем chat_id"""
        chat_id = self.telegram_chat_id_input.text().strip()
        
        if not chat_id:
            # Пустое поле - серая рамка
            self._set_api_input_style(self.telegram_chat_id_input, "empty")
            return
        
        # Получаем токен для полной проверки, если он валиден
        token = None
        token_text = self.telegram_token_input.text().strip()
        if token_text:
            token_success, _ = self._validate_telegram_token(token_text)
            if token_success:
                token = token_text
        
        # Валидация chat_id
        success, error_message = self._validate_telegram_chat_id(chat_id, token)
        
        if success:
            self._set_api_input_style(self.telegram_chat_id_input, "success")
        else:
            self._set_api_input_style(self.telegram_chat_id_input, "error")
    
    def _on_cancel(self):
        """Обработчик кнопки 'Отмена'"""
        # Восстанавливаем исходную тему
        self.app.theme = self.initial_theme_var
        self.app._apply_theme()
        if self.on_close:
            self.on_close()
