from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from backup_state_manager import BackupStateManager
from ui.main_window_controller import MainWindowController


def _build_controller(state_manager: BackupStateManager) -> tuple[MainWindowController, Mock, Mock]:
    view = Mock()

    source_manager = Mock()
    source_manager.get_effective_source_type.return_value = "audio"
    source_manager.get_total_sources_size.return_value = 0

    view_model = Mock()
    view_model.has_basic_conditions.return_value = True

    file_selection_handler = Mock()

    size_service = Mock()
    size_service.size_ready = Mock()

    config = Mock()
    config.load.return_value = {"macos_notifications_enabled": True}

    file_system = Mock()

    controller = MainWindowController(
        view=view,
        state_manager=state_manager,
        source_manager=source_manager,
        view_model=view_model,
        file_selection_handler=file_selection_handler,
        size_service=size_service,
        config=config,
        file_system=file_system,
    )
    return controller, view, source_manager


@patch("ui.main_window_controller.NotificationManager")
def test_set_source_type_updates_state_and_rerenders(
    _mock_notification_manager_class: Mock, tmp_path: Path
) -> None:
    state_manager = BackupStateManager()
    source = tmp_path / "source_type_case"
    source.mkdir()
    state_manager.add_source_path(str(source))

    controller, view, source_manager = _build_controller(state_manager)
    source_manager.get_effective_source_type.return_value = "audio"

    controller.set_source_type(str(source) + "/", "audio")

    assert state_manager.get_source_type(str(source)) == "audio"
    view.render_source_type.assert_called_once_with(str(source), source_type="audio")


@patch("ui.main_window_controller.NotificationManager")
def test_remove_source_works_with_noncanonical_input(
    _mock_notification_manager_class: Mock, tmp_path: Path
) -> None:
    state_manager = BackupStateManager()
    source = tmp_path / "remove_case"
    source.mkdir()
    state_manager.add_source_path(str(source))

    controller, view, source_manager = _build_controller(state_manager)

    controller.remove_source(str(source) + "/")

    assert state_manager.has_sources() is False
    source_manager.remove_source_size.assert_called_once_with(str(source))
    source_manager.remove_folder_category.assert_called_once_with(str(source))
    view.render_remove_source.assert_called_once_with(str(source))
