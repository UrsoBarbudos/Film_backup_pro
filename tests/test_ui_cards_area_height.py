"""Тесты для cards_area_height и констант зоны карточек."""

from ui.ui_constants import UISizes, UISpacing, cards_area_height, main_window_content_height


def test_cards_area_height_zero():
    assert cards_area_height(0) == 0


def test_cards_area_height_one():
    assert cards_area_height(1) == 72


def test_cards_area_height_two():
    assert cards_area_height(2) == 128


def test_cards_area_height_three():
    # 3 карточки + 0.5 = 3.5 карточки: 3*48 + 2*8 + 24 = 184
    assert cards_area_height(3) == 184


def test_cards_area_height_four():
    # 4 карточки + 0.5 = 4.5 карточки: 4*48 + 3*8 + 24 = 240
    assert cards_area_height(4) == 240


def test_cards_area_height_five():
    # Для 5 карточек: 5.5 карточек (до нового порога фикса)
    assert cards_area_height(5) == 296


def test_cards_area_height_six():
    # При 6 карточках используется фиксированная высота «6.5 карточек»
    assert cards_area_height(6) == 352


def test_cards_area_height_many():
    assert cards_area_height(10) == 352


def test_ui_sizes_cards_constants():
    assert UISizes.SOURCE_ITEM_HEIGHT == 48
    assert UISizes.CARDS_LIST_SPACING == 8
    assert UISizes.CARDS_VISIBLE_COUNT == 6
    assert UISizes.CARDS_AREA_MAX_HEIGHT == 352


def test_main_window_content_height_changes_only_by_cards_area():
    assert (
        main_window_content_height(3) - main_window_content_height(0)
        == cards_area_height(3)
    )
