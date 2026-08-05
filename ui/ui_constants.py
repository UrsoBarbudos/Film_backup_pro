"""Константы для UI spacing и размеров"""

class UISpacing:
    """Константы spacing между элементами"""
    TOP = 32           # После верхних кнопок
    SECTION = 8        # Между секциями
    INTERNAL = 8       # Внутри секций
    BUTTONS = 16       # Перед кнопками (через margin)

class UISizes:
    """Константы размеров элементов"""
    HEADER_HEIGHT = 24
    INPUT_HEIGHT = 40
    DROP_ZONE_HEIGHT = 160
    BUTTON_HEIGHT = 40
    SOURCE_ITEM_HEIGHT = 48
    CARDS_LIST_SPACING = 8
    CARDS_VISIBLE_COUNT = 6
    CARDS_AREA_MAX_HEIGHT = (
        CARDS_VISIBLE_COUNT * SOURCE_ITEM_HEIGHT
        + (CARDS_VISIBLE_COUNT - 1) * CARDS_LIST_SPACING
        + (SOURCE_ITEM_HEIGHT // 2)
    )  # 6.5 карточек = 352
    TOP_BAR_HEIGHT = 28
    DESTINATION_ROW_HEIGHT = 48

class UIMargins:
    """Константы отступов layout'ов"""
    MAIN_LAYOUT = (16, 16, 16, 16)  # left, top, right, bottom
    CONTENT_INSET_H = 12  # горизонтальный отступ контента в секциях (слева/справа)

class UIAnimation:
    """Константы анимаций"""
    TRANSITION_DURATION_MS = 300
    PROGRESS_PAGE_HEIGHT = 350
    PROGRESS_SCALE = 10_000
    PROGRESS_DURATION_MS = 150
    SPEED_UPDATE_INTERVAL_MS = 200
    ETA_UPDATE_INTERVAL_MS = 750
    COPY_ACTIVITY_UPDATE_INTERVAL_MS = 225
    COPY_ACTIVITY_IDLE_TIMEOUT_MS = 3_000
    COPY_ACTIVITY_WATCH_INTERVAL_MS = 250


def cards_area_height(count: int) -> int:
    """Высота зоны карточек: 0 -> 0, 1..6 -> N+0.5 карточек, 6+ -> фикс 6.5."""
    if count <= 0:
        return 0
    if count < UISizes.CARDS_VISIBLE_COUNT:
        return (
            count * UISizes.SOURCE_ITEM_HEIGHT
            + (count - 1) * UISizes.CARDS_LIST_SPACING
            + (UISizes.SOURCE_ITEM_HEIGHT // 2)
        )
    return UISizes.CARDS_AREA_MAX_HEIGHT


def main_window_content_height(card_count: int) -> int:
    """Минимальная высота контента главного окна (новый UI) при заданном числе карточек исходников."""
    top_bottom_margins = UIMargins.MAIN_LAYOUT[1] + UIMargins.MAIN_LAYOUT[3]
    sources_header_height = (
        UISizes.HEADER_HEIGHT * 2
        + UISpacing.INTERNAL * 2
        + UISizes.DROP_ZONE_HEIGHT
    )
    cards_to_dest_spacing = UISpacing.SECTION * 2
    dest_section_height = UISizes.HEADER_HEIGHT + UISpacing.INTERNAL + UISizes.DESTINATION_ROW_HEIGHT
    buttons_section_height = UISpacing.BUTTONS + UISizes.BUTTON_HEIGHT
    fixed_part = (
        top_bottom_margins
        + UISizes.TOP_BAR_HEIGHT
        + UISpacing.TOP
        + sources_header_height
        + cards_to_dest_spacing
        + dest_section_height
        + buttons_section_height
    )
    return fixed_part + cards_area_height(card_count)
