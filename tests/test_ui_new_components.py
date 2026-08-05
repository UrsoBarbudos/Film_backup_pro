"""Тесты для компонентов нового UI (ui_new)."""

import pytest
from unittest.mock import Mock
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from ui.ui_constants import cards_area_height


def _make_progress_page(qtbot):
    from progress_window import ProgressPage

    app = Mock()
    app.theme = "light"
    page = ProgressPage(parent=None, app_instance=app)
    qtbot.addWidget(page)
    return page


def test_progress_bar_uses_high_resolution_and_fractional_target(qapp, qtbot):
    page = _make_progress_page(qtbot)

    page._set_progress_target(41.37)

    assert page.progress_bar.maximum() == 10_000
    assert page._progress_animation.endValue() == 4_137


def test_progress_target_is_monotonic_and_restarts_from_current_value(qapp, qtbot):
    page = _make_progress_page(qtbot)
    page._set_progress_target(10.0)
    QTest.qWait(30)
    current_value = page.progress_bar.value()

    page._set_progress_target(10.5)
    assert page._progress_animation.startValue() == current_value
    page._set_progress_target(10.4)
    assert page._last_confirmed_progress_value == 1_050
    page._set_progress_target(11.0)
    assert page._last_confirmed_progress_value == 1_100


def test_progress_packet_updates_widgets_only_through_viewmodel(qapp, qtbot):
    page = _make_progress_page(qtbot)
    original_update = page._update_ui_directly_from_mb
    page._update_ui_directly_from_mb = Mock(wraps=original_update)

    page._on_progress_updated(25.0, 25.0, 100.0, 80.0, "/tmp/clip.mov")
    qapp.processEvents()

    page._update_ui_directly_from_mb.assert_called_once()
    assert page.speed_label.text() == "Скорость: 80.00 МБ/с"


def test_progress_speed_and_eta_are_throttled_to_latest_text(qapp, qtbot):
    page = _make_progress_page(qtbot)
    page._update_speed_if_due("speed-1")
    page._update_speed_if_due("speed-2")
    page._update_eta_if_due("eta-1")
    page._update_eta_if_due("eta-2")

    assert page.speed_label.text() == "speed-1"
    assert page.time_label.text() == "eta-1"
    QTest.qWait(800)
    assert page.speed_label.text() == "speed-2"
    assert page.time_label.text() == "eta-2"


def test_progress_pause_stops_animation_and_reset_clears_state(qapp, qtbot):
    page = _make_progress_page(qtbot)
    page._set_progress_target(50.0)
    QTest.qWait(20)

    page.view_model.set_paused(True)
    qapp.processEvents()
    paused_value = page.progress_bar.value()
    QTest.qWait(200)
    assert page.progress_bar.value() == paused_value
    assert page.time_label.text() == "Осталось времени: Пауза"

    page._reset_progress_display()
    assert page.progress_bar.value() == 0
    assert page._last_confirmed_progress_value == 0
    assert not page._speed_update_timer.isActive()
    assert not page._eta_update_timer.isActive()


def test_progress_reaches_full_only_after_confirmed_success(qapp, qtbot):
    from backup_components.completion_status import BackupCompletionStatus

    page = _make_progress_page(qtbot)
    page._set_progress_target(100.0)
    QTest.qWait(200)
    assert page.progress_bar.value() == 9_999
    assert page.progress_percent_label.text() != "100%"

    page._on_finished(BackupCompletionStatus.SUCCESS.value, "done", {})
    assert page.progress_bar.value() == 10_000
    assert page.progress_percent_label.text() == "100%"


def test_cancelled_progress_does_not_animate_to_full(qapp, qtbot):
    from backup_components.completion_status import BackupCompletionStatus

    page = _make_progress_page(qtbot)
    page._set_progress_target(60.0)
    QTest.qWait(30)
    page._on_finished(BackupCompletionStatus.CANCELLED.value, "cancelled", {})
    cancelled_value = page.progress_bar.value()
    QTest.qWait(200)

    assert page.progress_bar.value() == cancelled_value
    assert page.progress_bar.value() < 10_000


def test_copy_activity_updates_from_growing_copied_bytes(qapp, qtbot):
    from utils import format_size

    page = _make_progress_page(qtbot)
    copied = 10 * 1024 * 1024
    total = 100 * 1024 * 1024

    page._update_copy_activity(copied, total, 25.0)

    assert page.copied_label.text() == (
        f"Скопировано {format_size(copied)} из {format_size(total)} · 25.00 МБ/с"
    )


def test_standalone_speed_row_stays_hidden_after_reset(qapp, qtbot):
    page = _make_progress_page(qtbot)
    page.show()
    page._reset_ui_state()

    assert page.speed_label.isHidden()
    assert "МБ/с" in page._format_copy_activity(1, 10, 25.0)


def test_copy_activity_throttle_keeps_latest_snapshot(qapp, qtbot):
    from utils import format_size

    page = _make_progress_page(qtbot)
    mib = 1024 * 1024
    page._update_copy_activity(10 * mib, 100 * mib, 20.0)
    first_text = page.copied_label.text()
    page._update_copy_activity(20 * mib, 100 * mib, 30.0)
    page._update_copy_activity(30 * mib, 100 * mib, 40.0)

    assert page.copied_label.text() == first_text
    QTest.qWait(260)
    assert page.copied_label.text() == (
        f"Скопировано {format_size(30 * mib)} из {format_size(100 * mib)} · 40.00 МБ/с"
    )


def test_copy_activity_filename_changes_immediately(qapp, qtbot):
    page = _make_progress_page(qtbot)
    page._update_ui_directly_from_mb(10.0, 10.0, 100.0, 20.0, "/tmp/first.mov")
    page._update_ui_directly_from_mb(11.0, 11.0, 100.0, 20.0, "/tmp/second.mov")

    assert page.current_file_label.text() == "second.mov"


def test_copy_activity_does_not_set_identical_text_twice(qapp, qtbot):
    page = _make_progress_page(qtbot)
    original_set_text = page.copied_label.setText
    page.copied_label.setText = Mock(wraps=original_set_text)
    text = "Скопировано 1.00 МБ · 1.00 МБ/с"

    page._update_copy_activity_text(text, force=True)
    page._update_copy_activity_text(text, force=True)

    page.copied_label.setText.assert_called_once_with(text)


def test_pause_blocks_copy_activity_updates(qapp, qtbot):
    page = _make_progress_page(qtbot)
    page.view_model.set_paused(True)
    qapp.processEvents()
    previous_text = page.copied_label.text()

    page._update_copy_activity(20 * 1024 * 1024, 100 * 1024 * 1024, 30.0)

    assert page.copied_label.text() == previous_text
    assert not page._copy_activity_timer.isActive()


def test_finished_copy_activity_cannot_be_overwritten_by_pending_text(qapp, qtbot):
    from backup_components.completion_status import BackupCompletionStatus

    page = _make_progress_page(qtbot)
    page._update_copy_activity_text("first", force=True)
    page._update_copy_activity_text("pending")
    page._on_finished(BackupCompletionStatus.SUCCESS.value, "done", {})
    final_text = page.copied_label.text()

    QTest.qWait(300)
    assert page.copied_label.text() == final_text
    assert not page._copy_activity_timer.isActive()


def test_copy_activity_shows_waiting_and_recovers_on_growth(qapp, qtbot):
    from utils import format_size

    page = _make_progress_page(qtbot)
    mib = 1024 * 1024
    page._update_copy_activity(10 * mib, 100 * mib, 20.0)
    page._last_copy_growth_time -= 3.1

    page._check_copy_activity()
    assert page.copied_label.text() == "Ожидание данных…"

    page._update_copy_activity(11 * mib, 100 * mib, 20.0)
    assert page.copied_label.text() == (
        f"Скопировано {format_size(11 * mib)} из {format_size(100 * mib)} · 20.00 МБ/с"
    )


def test_copy_activity_reset_clears_previous_operation(qapp, qtbot):
    page = _make_progress_page(qtbot)
    page._update_copy_activity(10, 100, 1.0)
    page._update_copy_activity(20, 100, 2.0)

    page._reset_progress_display()

    assert page._last_activity_copied_bytes is None
    assert page._last_copy_growth_time is None
    assert page._pending_copy_activity_text is None
    assert not page._copy_activity_timer.isActive()
    assert not page._copy_activity_watch_timer.isActive()


def test_sources_header_and_drop_widget_has_attributes(qapp, qtbot):
    from ui_new.components import SourcesHeaderAndDropWidget
    widget = SourcesHeaderAndDropWidget(parent=None, app_instance=Mock())
    qtbot.addWidget(widget)
    assert widget.sources_drop is not None
    assert widget.total_size_label is not None


def test_compact_decision_dialog_reject_is_safe_default(qapp, qtbot):
    from compact_decision_dialog import CompactDecisionDialog, DecisionAction

    dialog = CompactDecisionDialog(
        None,
        title="Этот носитель уже копировался",
        text="На носителе найдена подтверждённая отметка Дублёра.",
        actions=(
            DecisionAction("cancel", "Не добавлять"),
            DecisionAction("add", "Добавить повторно"),
        ),
        reject_action="cancel",
    )
    qtbot.addWidget(dialog)
    dialog.reject()
    assert dialog.selected_action == "cancel"


def test_sources_cards_widget_has_attributes(qapp, qtbot):
    from ui_new.components import SourcesCardsWidget
    widget = SourcesCardsWidget(parent=None, app_instance=Mock())
    qtbot.addWidget(widget)
    assert widget.sources_list_widget is not None
    assert widget.sources_list_layout is not None


def test_source_item_layout_order_and_values(qapp, qtbot):
    from widgets.source_item import SourceItem

    app_mock = Mock()
    app_mock.theme = "light"
    item = SourceItem(
        "/tmp/card_1",
        app_mock,
        size_bytes=640 * 1024 * 1024,
        source_type="video",
    )
    qtbot.addWidget(item)

    assert item.volume_title_label.text() == "Volume"
    assert item.volume_value_label.text() == "card_1"
    assert item.size_title_label.text() == "Size"
    assert item.type_title_label.text() == "Type"
    assert item.type_tag_button.text() == "VIDEO"

    layout = item.layout()
    assert layout.itemAt(0).widget() is item.type_widget
    assert layout.itemAt(1).widget().objectName() == "SourceItemInfoWidget"
    assert layout.itemAt(2).widget() is item.remove_btn
    item.deleteLater()


def test_source_item_type_dropdown_emits_change(qapp, qtbot):
    from widgets.source_item import SourceItem

    app_mock = Mock()
    app_mock.theme = "light"
    item = SourceItem("/tmp/card_2", app_mock, size_bytes=1, source_type="video")
    qtbot.addWidget(item)

    captured = []
    item.source_type_changed.connect(lambda path, source_type: captured.append((path, source_type)))
    item.type_tag_button.click()
    item.type_combo.setCurrentText("AUDIO")

    assert item.type_tag_button.text() == "AUDIO"
    assert captured == [("/tmp/card_2", "audio")]
    item.deleteLater()


def test_app_new_remove_cross_smoke_after_layout_change(qapp, qtbot):
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    context = build_app_context()
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()

    source_path = "/tmp/remove_smoke_source"
    window.state_manager.add_source_path(source_path)
    window.render_add_source(source_path, size_bytes=0, source_type="video", animated=False)
    assert len(window._source_items) == 1

    item = next(iter(window._source_items.values()))
    item.remove_btn.click()
    QTest.qWait(50)

    assert len(window._source_items) == 0
    window.close()


def test_sources_cards_widget_update_height_zero(qapp, qtbot):
    from ui_new.components import SourcesCardsWidget
    widget = SourcesCardsWidget(parent=None, app_instance=Mock())
    qtbot.addWidget(widget)
    widget.update_height(0)
    assert int(widget._animated_height) == cards_area_height(0)


def test_sources_cards_widget_update_height_three(qapp, qtbot):
    from ui_new.components import SourcesCardsWidget
    widget = SourcesCardsWidget(parent=None, app_instance=Mock())
    qtbot.addWidget(widget)
    widget.update_height(3)
    assert int(widget._height_animation.endValue()) == cards_area_height(3)


def test_sources_cards_widget_update_height_six(qapp, qtbot):
    from ui_new.components import SourcesCardsWidget
    widget = SourcesCardsWidget(parent=None, app_instance=Mock())
    qtbot.addWidget(widget)
    widget.update_height(6)
    assert int(widget._height_animation.endValue()) == cards_area_height(6)


def test_sources_cards_widget_visibility_animation(qapp, qtbot):
    from ui_new.components import SourcesCardsWidget

    widget = SourcesCardsWidget(parent=None, app_instance=Mock())
    qtbot.addWidget(widget)
    assert widget._opacity_effect.opacity() == pytest.approx(0.0, abs=0.05)

    widget.update_height(1)
    QTest.qWait(350)
    assert widget.isHidden() is False
    assert widget._opacity_effect.opacity() == pytest.approx(1.0, abs=0.05)

    widget.update_height(0)
    QTest.qWait(350)
    assert widget.isHidden() is True
    assert widget._opacity_effect.opacity() == pytest.approx(0.0, abs=0.05)


def test_app_new_backward_compat_attributes_and_layout(qapp, qtbot):
    """Smoke: AppNew создаётся, атрибуты backward compatibility есть, в layout два stretch."""
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    context = build_app_context()
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()

    assert window.sources_drop is not None
    assert window.total_size_label is not None
    assert window.sources_list_widget is not None
    assert window.sources_list_layout is not None

    central = window.centralWidget()
    assert central is not None
    central_layout = central.layout()
    assert central_layout is not None
    assert central_layout.count() == 1
    assert window.stacked.currentWidget() is window.main_page


def test_app_new_render_sources_updates_cards_height(qapp, qtbot):
    """После render_sources и render_add_source высота зоны соответствует новой baseline-логике."""
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    context = build_app_context()
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()

    window.render_sources([])
    QTest.qWait(50)
    assert window.sources_cards._animated_height == cards_area_height(0)
    assert window.sources_header.isHidden() is False
    assert window.sources_drop.isHidden() is False
    assert window.sources_cards.isHidden() is True

    window.render_add_source("/tmp/test_source", size_bytes=0, animated=False)
    QTest.qWait(350)
    assert len(window._source_items) == 1
    assert window.sources_cards._animated_height == cards_area_height(1)
    assert window.sources_cards.isHidden() is False


def test_reset_after_backup_clears_session_and_returns_to_empty_main(qapp, qtbot):
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    context = build_app_context()
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()
    window.state_manager.add_source_path("/tmp/card")
    window.state_manager.set_destination_path("/tmp/backup")
    window.render_add_source("/tmp/card", size_bytes=1024, animated=False)
    window.stacked.setCurrentWidget(window.progress_page)

    window.reset_after_backup()
    QTest.qWait(700)

    assert window.stacked.currentWidget() is window.main_page
    assert window.state_manager.source_paths == []
    assert window.state_manager.destination_path is None
    assert len(window._source_items) == 0
    assert window.centralWidget().graphicsEffect() is None
    assert not window.sources_drop.animation_label.pixmap().isNull()
    window.close()


def test_transition_to_progress_uses_fixed_height(qapp, qtbot):
    from composition import build_app_context
    from ui.ui_constants import UIAnimation
    from ui_new.main_window_new import AppNew

    context = build_app_context()
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()
    window.resize(window.width(), 800)

    window.start_transition_to_progress()
    QTest.qWait(700)

    assert window.stacked.currentWidget() is window.progress_page
    assert window.height() == UIAnimation.PROGRESS_PAGE_HEIGHT
    window.close()


def test_successful_eject_returns_to_start_screen(qapp, qtbot, monkeypatch):
    from composition import build_app_context
    from disk_ejector import EjectResult
    from ui_new.main_window_new import AppNew

    context = build_app_context()
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()
    window.state_manager.add_source_path("/Volumes/CARD_A/DCIM")
    window.state_manager.set_destination_path("/tmp/backup")
    window.render_add_source("/Volumes/CARD_A/DCIM", size_bytes=1024, animated=False)
    window.progress_page.source_paths = ["/Volumes/CARD_A/DCIM"]
    window.stacked.setCurrentWidget(window.progress_page)
    window.progress_page.finish_button.show()
    QTest.qWait(20)

    monkeypatch.setattr(
        "progress_window.eject_volume",
        lambda volume: EjectResult(volume, True, "Disk ejected"),
    )

    window.progress_page._on_eject_clicked()
    QTest.qWait(700)

    assert window.stacked.currentWidget() is window.main_page
    assert window.state_manager.source_paths == []
    assert window.state_manager.destination_path is None
    window.close()


def test_app_new_ignores_legacy_copy_mode_and_has_single_copy_ui(tmp_path, qapp, qtbot):
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"copy_mode": "logging"}', encoding="utf-8")

    context = build_app_context(settings_file=str(settings_file))
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()

    assert not hasattr(window, "copy_mode")
    assert not hasattr(window, "copy_mode_section")
    assert not hasattr(window, "project_name_entry")
    assert not hasattr(window, "project_name_section")


def test_app_new_start_uses_only_destination_and_sources(tmp_path, qapp, qtbot):
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    settings_file = tmp_path / "settings.json"
    context = build_app_context(settings_file=str(settings_file))
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()

    window.state_manager.set_destination_path("/tmp/destination")
    window.state_manager.add_source_path("/tmp/source-a")
    window.backup_controller.start_new_backup = Mock()

    window.start_the_backup()
    kwargs = window.backup_controller.start_new_backup.call_args.kwargs
    assert kwargs == {
        "destination_root": "/tmp/destination",
        "source_drives": ["/tmp/source-a"],
    }


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Enter])
def test_app_new_enter_starts_enabled_backup(key, tmp_path, qapp, qtbot):
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    context = build_app_context(settings_file=str(tmp_path / "settings.json"))
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    window.setFocus()
    qapp.processEvents()
    window.start_button.setEnabled(True)
    window.backup_controller.start_new_backup = Mock()

    QTest.keyClick(window, key)

    window.backup_controller.start_new_backup.assert_called_once()


def test_app_new_enter_does_not_start_disabled_backup(tmp_path, qapp, qtbot):
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    context = build_app_context(settings_file=str(tmp_path / "settings.json"))
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    window.setFocus()
    qapp.processEvents()
    assert window.start_button.isEnabled() is False
    window.backup_controller.start_new_backup = Mock()

    QTest.keyClick(window, Qt.Key_Return)

    window.backup_controller.start_new_backup.assert_not_called()


def test_app_new_enter_does_not_start_from_progress_page(tmp_path, qapp, qtbot):
    from composition import build_app_context
    from ui_new.main_window_new import AppNew

    context = build_app_context(settings_file=str(tmp_path / "settings.json"))
    window = AppNew(context=context)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    window.setFocus()
    qapp.processEvents()
    window.start_button.setEnabled(True)
    window.stacked.setCurrentWidget(window.progress_page)
    window.backup_controller.start_new_backup = Mock()

    QTest.keyClick(window, Qt.Key_Return)

    window.backup_controller.start_new_backup.assert_not_called()
