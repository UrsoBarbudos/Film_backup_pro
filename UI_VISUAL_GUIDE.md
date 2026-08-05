# Подробная инструкция: как работать с визуалом UI в Dублёр

Этот документ описывает, где и как менять внешний вид приложения (цвета, отступы, виджеты, темы), чтобы вы могли экспериментировать с UI самостоятельно.

---

## 1. Общая картина

- **Фреймворк:** PySide6 (Qt для Python).
- **Стиль приложения:** `app.setStyle("Fusion")` в `app.py` — выбран специально, чтобы кастомизировать чекбоксы и другие элементы (нативный стиль macOS это блокирует).
- **Визуал задаётся:**
  1. **Темами** — `themes.py` (светлая/тёмная тема, цвета кнопок).
  2. **Константами отступов и размеров** — `ui/ui_constants.py`.
  3. **Компонентами главного окна** — `ui_new/components/` (секции интерфейса).
  4. **Кастомными виджетами** — `widgets/` (кнопки-ссылки, дропзоны, карточки источников и т.д.).
  5. **Локальными стилями** — через `setStyleSheet()` у отдельных виджетов.

Главное окно собирается в **`ui_new/main_window_new.py`**: создаётся центральный виджет, в него по вертикали добавляются секции из `ui_new/components/`.

---

## 2. Где что лежит (быстрая навигация)

| Что хотите изменить | Файл / папка |
|---------------------|--------------|
| Цвет фона окна, кнопок, полей ввода, общий вид светлой/тёмной темы | `themes.py` |
| Отступы между секциями, высоты заголовков, кнопок, дропзоны | `ui/ui_constants.py` |
| Верхние кнопки «Настройки» и «Очистить все» | `ui_new/components/top_buttons_widget.py` |
| Заголовок «Источники», дропзона, подпись «Общий объём» | `ui_new/components/sources_header_and_drop_widget.py` |
| Список карточек источников и анимации | `ui_new/components/sources_cards_widget.py`, `source_card_slide_wrapper.py` |
| Блок «Папка назначения» | `ui_new/components/destination_section_widget.py` |
| Кнопка «Начать копирование» | `ui_new/components/buttons_section_widget.py` |
| Внешний вид одной карточки источника | `widgets/source_item.py` |
| Кнопки-ссылки (Настройки, Очистить все) | `widgets/link_button.py` |
| Зона перетаскивания (drag-and-drop) | `widgets/drop_zone.py` |
| Виджет назначения (путь + место на диске) | `widgets/integrated_destination_widget.py` |
| Диалоги «О программе», приветствие | `ui_forms/` (`.py` + при необходимости `.ui` из Qt Designer) |

---

## 3. Темы: цвета и общий стиль

### 3.1 Файл `themes.py`

- **`ThemeManager.get_main_window_stylesheet(theme)`** — возвращает одну большую строку со стилями в формате Qt Style Sheets (похоже на CSS) для:
  - `QMainWindow`, `QWidget`, `QLabel`, `QLineEdit`, `QPushButton`, `QScrollArea`
  - отдельно для `theme='light'` и `theme='dark'`.
- **`ThemeManager.get_green_button_color()`** — цвет активной кнопки «Начать копирование» (сейчас `#2FA572`).
- **`ThemeManager.get_red_button_color()`** / **`get_red_button_color_with_opacity()`** — цвет неактивной кнопки «Начать копирование».

**Как экспериментировать:**

1. Откройте `themes.py`.
2. В `get_main_window_stylesheet()` для `'light'` или `'dark'` поменяйте, например:
   - `background-color` у `QMainWindow` / `QWidget` — фон окна;
   - `color` у `QLabel` — цвет текста;
   - `background-color`, `border` у `QLineEdit` — поля ввода;
   - `background-color`, `border-radius`, `padding` у `QPushButton` и `QPushButton:hover`, `QPushButton:disabled`.
3. Сохраните файл и перезапустите приложение (или переключите тему в настройках, если уже есть переключатель).

Тема применяется в главном окне в методе **`_apply_theme()`** в `main_window_new.py`: вызывается `self.setStyleSheet(ThemeManager.get_main_window_stylesheet(self.theme))`, плюс обновляются виджеты, которые хранят тему у себя (например, карточки источников, секция назначения).

---

## 4. Отступы и размеры

### 4.1 Файл `ui/ui_constants.py`

- **`UISpacing`** — отступы:
  - `TOP` — после верхних кнопок;
  - `SECTION` — между секциями;
  - `INTERNAL` — внутри секции;
  - `BUTTONS` — отступ перед блоком кнопок.
- **`UISizes`** — высоты и размеры:
  - `HEADER_HEIGHT` — высота заголовка секции;
  - `INPUT_HEIGHT` — высота поля ввода;
  - `DROP_ZONE_HEIGHT` — высота зоны перетаскивания;
  - `BUTTON_HEIGHT` — высота кнопки «Начать копирование»;
  - `SOURCE_ITEM_HEIGHT` — высота одной карточки источника;
  - `CARDS_LIST_SPACING` — расстояние между карточками;
  - `CARDS_VISIBLE_COUNT`, `CARDS_AREA_MAX_HEIGHT` — сколько карточек показывать без скролла и максимальная высота области карточек.
- **`UIMargins.MAIN_LAYOUT`** — отступы центрального layout главного окна (left, top, right, bottom).

**Как экспериментировать:**

1. Измените, например, `UISpacing.SECTION` или `UIMargins.MAIN_LAYOUT` — сразу изменится «воздух» между блоками и от краёв окна.
2. Измените `UISizes.DROP_ZONE_HEIGHT` или `SOURCE_ITEM_HEIGHT` — изменится высота дропзоны и карточек.
3. Перезапустите приложение и посмотрите результат.

Функции **`cards_area_height(count)`** и **`main_window_content_height(card_count)`** считают высоту области карточек и минимальную высоту окна — они опираются на эти константы, поэтому при изменении размеров логично сверяться с ними.

---

## 5. Секции главного окна (`ui_new/components/`)

Главное окно не рисует всё «вручную» в одном файле, а собирает готовые виджеты-секции:

1. **TopButtonsWidget** — «Настройки», «Очистить все».
2. **SourcesHeaderAndDropWidget** — заголовок «Источники», дропзона, «Общий объём».
3. **SourcesCardsWidget** — контейнер со списком карточек источников.
4. **DestinationSectionWidget** — заголовок «Папка назначения» и виджет пути/диска.
5. **ButtonsSectionWidget** — кнопка «Начать копирование».

Они добавляются в **`_create_ui()`** в `main_window_new.py` в `main_layout` с помощью `addWidget()` и `addSpacing()`. Порядок и отступы между ними заданы там же (используются `UISpacing`, `UIMargins` из `ui_constants`).

**Как экспериментировать:**

- Чтобы изменить текст, размеры или расположение элементов **внутри** одной секции — откройте соответствующий файл в `ui_new/components/` (например, `buttons_section_widget.py`, `destination_section_widget.py`).
- Чтобы изменить отступы **между** секциями — в `main_window_new.py` в `_create_ui()` поменяйте аргументы `addSpacing(...)` или отступы в самих виджетах (через `setContentsMargins` у их layout).
- Чтобы добавить новую секцию — создайте новый виджет в `ui_new/components/`, добавьте его в `__init__.py` компонентов, затем в `_create_ui()` создайте экземпляр и вставьте в `main_layout` в нужное место.

---

## 7. Кнопка «Начать копирование»

- Внешний вид (размер, отступы) задаётся в **`ui_new/components/buttons_section_widget.py`**: создаётся `QPushButton`, задаётся `setFixedHeight(UISizes.BUTTON_HEIGHT)`, отступы layout берутся из `UISpacing`.
- Цвета активной/неактивной кнопки задаются в **`main_window_new.py`** в методах **`_enable_start_button()`** и **`_disable_start_button()`**: там вызываются `ThemeManager.get_green_button_color()` и `ThemeManager.get_red_button_color_with_opacity()` и подставляются в `setStyleSheet()`.

**Как экспериментировать:**

- Цвет только кнопки — меняйте в `themes.py` методы `get_green_button_color()` / `get_red_button_color_with_opacity()` или сами строки в `_enable_start_button()` / `_disable_start_button()`.
- Размер, скругление, отступы — в `buttons_section_widget.py` можно добавить виджету `setObjectName()` и задать стили в `themes.py` для этого объекта, либо вызвать `setStyleSheet()` прямо в виджете с нужными `padding`, `border-radius` и т.д.

---

## 8. Кастомные виджеты (`widgets/`)

- **LinkButton** — кнопки «Настройки», «Очистить все»; стили для них в `themes.py` заданы через `QPushButton#SettingsLinkButton`.
- **DropZone** — зона перетаскивания; собственные стили обычно задаются внутри виджета или через тему.
- **SourceItem** — карточка одного источника; тема и стили применяются в методе `_apply_theme_styles()` (главное окно передаёт тему и вызывает обновление при смене темы).
- **IntegratedDestinationWidget** — путь назначения и информация о диске; при смене темы вызывается `update_theme()` из главного окна.

Если хотите изменить внешний вид конкретного элемента (например, карточки источника) — откройте соответствующий файл в `widgets/` и ищите `setStyleSheet`, `setFixedHeight`, цвета и шрифты.

---

## 9. Диалоги и формы Qt Designer (`ui_forms/`)

- В `ui_forms/` лежат диалоги (например, приветствие, «О программе»). Могут быть файлы `.ui` (разметка из Qt Designer) и `.py` (логика и загрузка формы).
- Чтобы менять разметку визуально — открывайте `.ui` в **Qt Designer** (идёт с PySide6: обычно `pyside6-designer` или через IDE). Сохраняете `.ui`, при необходимости обновляете код в `.py`, если меняли имена виджетов или структуру.
- Стили диалогов можно задавать в коде при показе (как в `render_user_message()` в главном окне — там задаётся `setStyleSheet` для `QMessageBox` в зависимости от темы).

---

## 10. Пошаговые сценарии «с чего начать»

### Сценарий A: Поменять цвета темы (например, фон и кнопки)

1. Открыть `themes.py`.
2. Найти `get_main_window_stylesheet()` и нужную тему (`'light'` или `'dark'`).
3. Поменять `background-color` у `QMainWindow`/`QWidget`, цвета у `QPushButton` и т.д.
4. Сохранить и перезапустить приложение.

### Сценарий B: Увеличить или уменьшить отступы между блоками

1. Открыть `ui/ui_constants.py` и изменить `UISpacing.SECTION` или `UISpacing.TOP`.
2. При желании подправить `UIMargins.MAIN_LAYOUT` в том же файле.
3. Перезапустить приложение.

### Сценарий C: Изменить высоту зоны перетаскивания или карточек

1. В `ui/ui_constants.py` изменить `UISizes.DROP_ZONE_HEIGHT` или `UISizes.SOURCE_ITEM_HEIGHT`, при необходимости `CARDS_VISIBLE_COUNT` и `CARDS_AREA_MAX_HEIGHT`.
2. Перезапустить приложение.

### Сценарий E: Изменить текст или расположение кнопок в секции

1. Открыть нужный файл в `ui_new/components/` (например, `top_buttons_widget.py` или `buttons_section_widget.py`).
2. Поменять надписи кнопок, добавить/убрать виджеты в layout, подправить `addStretch()`, отступы.
3. Перезапустить приложение.

---

## 11. Важные замечания

- После изменений в коде или в `.ui` приложение нужно **перезапустить**, чтобы увидеть результат (hot-reload в этом проекте не настроен).
- Стили задаются в формате **Qt Style Sheets**: синтаксис похож на CSS, но селекторы — это имена классов Qt (`QPushButton`, `QLabel`) и при необходимости `#objectName`. Официальная документация: [Qt Style Sheets](https://doc.qt.io/qt-6/stylesheet.html).
- Чтобы один виджет не наследовал общие стили окна, ему можно задать свой `setObjectName("UniqueId")` и в стилях использовать селектор `QWidget#UniqueId { ... }`.
- Для сложной вёрстки и анимаций используется код в Python (layout’ы, `QPropertyAnimation` и т.д.); для диалогов удобно использовать Qt Designer (`.ui`).

Если после правок что-то перестало отображаться или сломалось — проверьте, не удалили ли вы случайно привязку виджета к layout или не изменили ли `objectName`, на который опирается стиль или код в главном окне.
