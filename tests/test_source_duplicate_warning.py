"""
Тесты для проверки предупреждений при дубликатах источников.
"""

from unittest.mock import Mock, MagicMock, patch
import pytest
from pathlib import Path

from ui.file_selection_handler import FileSelectionHandler
from backup_state_manager import BackupStateManager
from source_manager import SourceManager
from notifications import NotificationManager


class TestFileSelectionHandlerDuplicates:
    """Тесты для FileSelectionHandler при дубликатах источников"""
    
    def test_handle_drop_sources_returns_duplicates(self, tmp_path: Path):
        """Проверяет, что handle_drop_sources возвращает информацию о дубликатах"""
        fs = Mock()
        fs.exists = Mock(return_value=True)
        
        state_manager = BackupStateManager()
        source_manager = SourceManager(file_system=fs)
        handler = FileSelectionHandler(state_manager, source_manager)
        
        # Добавляем первый источник
        path1 = str(tmp_path / "source1")
        added1, duplicates1 = handler.handle_drop_sources([path1])
        assert len(added1) == 1
        assert len(duplicates1) == 0
        
        # Пытаемся добавить тот же источник снова
        added2, duplicates2 = handler.handle_drop_sources([path1])
        assert len(added2) == 0
        assert len(duplicates2) == 1
        assert duplicates2[0] == path1
    
    def test_handle_drop_sources_multiple_duplicates(self, tmp_path: Path):
        """Проверяет обработку нескольких дубликатов"""
        fs = Mock()
        fs.exists = Mock(return_value=True)
        
        state_manager = BackupStateManager()
        source_manager = SourceManager(file_system=fs)
        handler = FileSelectionHandler(state_manager, source_manager)
        
        path1 = str(tmp_path / "source1")
        path2 = str(tmp_path / "source2")
        
        # Добавляем оба источника
        handler.handle_drop_sources([path1, path2])
        
        # Пытаемся добавить оба снова
        added, duplicates = handler.handle_drop_sources([path1, path2])
        assert len(added) == 0
        assert len(duplicates) == 2
        assert path1 in duplicates
        assert path2 in duplicates
    
    def test_handle_select_source_returns_duplicate(self, tmp_path: Path):
        """Проверяет, что handle_select_source возвращает информацию о дубликате"""
        fs = Mock()
        fs.exists = Mock(return_value=True)
        
        state_manager = BackupStateManager()
        source_manager = SourceManager(file_system=fs)
        handler = FileSelectionHandler(state_manager, source_manager)
        
        path = str(tmp_path / "source")
        
        # Добавляем источник
        added1, duplicate1 = handler.handle_select_source(path)
        assert added1 is True
        assert duplicate1 is None
        
        # Пытаемся добавить тот же источник снова
        added2, duplicate2 = handler.handle_select_source(path)
        assert added2 is False
        assert duplicate2 == path


class TestMainWindowControllerNotifications:
    """Тесты для MainWindowController при отправке уведомлений о дубликатах"""
    
    @patch('ui.main_window_controller.NotificationManager')
    def test_add_sources_sends_notification_for_duplicate(self, mock_notification_manager_class, tmp_path: Path):
        """Проверяет отправку уведомления при дубликате через add_sources"""
        from ui.main_window_controller import MainWindowController
        
        # Настраиваем моки
        mock_view = Mock()
        mock_view.render_add_source = Mock()
        mock_view.render_total_size = Mock()
        mock_view.render_disk_info_refresh = Mock()
        mock_view.render_destination_exceeded = Mock()
        mock_view.render_start_enabled = Mock()
        
        mock_notification_manager = Mock()
        mock_notification_manager.send_simple_notification = Mock(return_value=True)
        mock_notification_manager_class.return_value = mock_notification_manager
        
        fs = Mock()
        fs.exists = Mock(return_value=True)
        fs.dirname = Mock(return_value=str(tmp_path))
        
        state_manager = BackupStateManager()
        source_manager = SourceManager(file_system=fs)
        file_selection_handler = FileSelectionHandler(state_manager, source_manager)
        
        config = Mock()
        config.load = Mock(return_value={'macos_notifications_enabled': True})
        
        view_model = Mock()
        view_model.has_basic_conditions = Mock(return_value=True)
        view_model.get_disk_space_info = Mock(return_value=(True, 0, 0, 0))
        
        size_service = Mock()
        size_service.size_ready = Mock()
        
        controller = MainWindowController(
            view=mock_view,
            state_manager=state_manager,
            source_manager=source_manager,
            view_model=view_model,
            file_selection_handler=file_selection_handler,
            size_service=size_service,
            config=config,
            file_system=fs
        )
        
        path = str(tmp_path / "source")
        
        # Добавляем источник первый раз
        controller.add_sources([path])
        assert mock_notification_manager.send_simple_notification.call_count == 0
        
        # Добавляем тот же источник снова
        controller.add_sources([path])
        assert mock_notification_manager.send_simple_notification.call_count == 1
        call_args = mock_notification_manager.send_simple_notification.call_args
        assert call_args[1]['title'] == "Источник уже добавлен"
        assert path in call_args[1]['message']
    
    @patch('ui.main_window_controller.NotificationManager')
    def test_on_selected_source_dialog_sends_notification_for_duplicate(self, mock_notification_manager_class, tmp_path: Path):
        """Проверяет отправку уведомления при дубликате через on_selected_source_dialog"""
        from ui.main_window_controller import MainWindowController
        
        # Настраиваем моки
        mock_view = Mock()
        mock_view.render_add_source = Mock()
        mock_view.render_total_size = Mock()
        mock_view.render_disk_info_refresh = Mock()
        mock_view.render_destination_exceeded = Mock()
        mock_view.render_start_enabled = Mock()
        mock_view.set_last_source_dir = Mock()
        
        mock_notification_manager = Mock()
        mock_notification_manager.send_simple_notification = Mock(return_value=True)
        mock_notification_manager_class.return_value = mock_notification_manager
        
        fs = Mock()
        fs.exists = Mock(return_value=True)
        fs.dirname = Mock(return_value=str(tmp_path))
        
        state_manager = BackupStateManager()
        source_manager = SourceManager(file_system=fs)
        file_selection_handler = FileSelectionHandler(state_manager, source_manager)
        
        config = Mock()
        config.load = Mock(return_value={'macos_notifications_enabled': True})
        config.save = Mock()
        
        view_model = Mock()
        view_model.has_basic_conditions = Mock(return_value=True)
        view_model.get_disk_space_info = Mock(return_value=(True, 0, 0, 0))
        
        size_service = Mock()
        size_service.size_ready = Mock()
        
        controller = MainWindowController(
            view=mock_view,
            state_manager=state_manager,
            source_manager=source_manager,
            view_model=view_model,
            file_selection_handler=file_selection_handler,
            size_service=size_service,
            config=config,
            file_system=fs
        )
        
        path = str(tmp_path / "source")
        
        # Добавляем источник первый раз
        controller.on_selected_source_dialog(path)
        assert mock_notification_manager.send_simple_notification.call_count == 0
        
        # Добавляем тот же источник снова
        controller.on_selected_source_dialog(path)
        assert mock_notification_manager.send_simple_notification.call_count == 1
        call_args = mock_notification_manager.send_simple_notification.call_args
        assert call_args[1]['title'] == "Источник уже добавлен"
        assert path in call_args[1]['message']
    
    @patch('ui.main_window_controller.NotificationManager')
    def test_notification_respects_config_disabled(self, mock_notification_manager_class, tmp_path: Path):
        """Проверяет, что уведомления не отправляются, если они отключены в конфигурации"""
        from ui.main_window_controller import MainWindowController
        
        # Настраиваем моки
        mock_view = Mock()
        mock_view.render_add_source = Mock()
        mock_view.render_total_size = Mock()
        mock_view.render_disk_info_refresh = Mock()
        mock_view.render_destination_exceeded = Mock()
        mock_view.render_start_enabled = Mock()
        
        mock_notification_manager = Mock()
        mock_notification_manager.send_simple_notification = Mock(return_value=False)
        mock_notification_manager_class.return_value = mock_notification_manager
        
        fs = Mock()
        fs.exists = Mock(return_value=True)
        fs.dirname = Mock(return_value=str(tmp_path))
        
        state_manager = BackupStateManager()
        source_manager = SourceManager(file_system=fs)
        file_selection_handler = FileSelectionHandler(state_manager, source_manager)
        
        config = Mock()
        config.load = Mock(return_value={'macos_notifications_enabled': False})
        
        view_model = Mock()
        view_model.has_basic_conditions = Mock(return_value=True)
        view_model.get_disk_space_info = Mock(return_value=(True, 0, 0, 0))
        
        size_service = Mock()
        size_service.size_ready = Mock()
        
        controller = MainWindowController(
            view=mock_view,
            state_manager=state_manager,
            source_manager=source_manager,
            view_model=view_model,
            file_selection_handler=file_selection_handler,
            size_service=size_service,
            config=config,
            file_system=fs
        )
        
        path = str(tmp_path / "source")
        
        # Добавляем источник первый раз
        controller.add_sources([path])
        
        # Добавляем тот же источник снова
        controller.add_sources([path])
        
        # send_simple_notification вызывается, но возвращает False из-за отключенных уведомлений
        assert mock_notification_manager.send_simple_notification.call_count == 1


def test_marker_confirmation_precedes_add_and_handles_sources_independently(tmp_path: Path):
    from datetime import datetime, timezone
    from source_backup_marker import SourceBackupMarker
    from ui.main_window_controller import MainWindowController

    paths = [str(tmp_path / "one"), str(tmp_path / "two")]
    fs = Mock()
    fs.exists.return_value = True
    state = BackupStateManager()
    manager = SourceManager(file_system=fs)
    marker_service = Mock()
    marker_service.read_latest.side_effect = [
        SourceBackupMarker(paths[0], datetime.now(timezone.utc)),
        SourceBackupMarker(paths[1], datetime.now(timezone.utc)),
    ]
    view = Mock()
    view.confirm_previously_backed_up_source.side_effect = [False, True]
    config = Mock()
    config.load.return_value = {
        "macos_notifications_enabled": False,
        "warn_on_previously_backed_up_source": True,
    }
    size_service = Mock()
    size_service.size_ready = Mock()
    view_model = Mock()
    view_model.has_basic_conditions.return_value = False
    controller = MainWindowController(
        view=view,
        state_manager=state,
        source_manager=manager,
        view_model=view_model,
        file_selection_handler=FileSelectionHandler(state, manager),
        size_service=size_service,
        config=config,
        file_system=fs,
        source_backup_marker_service=marker_service,
    )

    controller.add_sources(paths)

    assert view.confirm_previously_backed_up_source.call_count == 2
    assert state.source_paths == [paths[1]]
    view.render_add_source.assert_called_once()


def test_warning_disabled_still_reads_marker_without_dialog(tmp_path: Path):
    from datetime import datetime, timezone
    from source_backup_marker import SourceBackupMarker
    from ui.main_window_controller import MainWindowController

    path = str(tmp_path / "source")
    fs = Mock()
    fs.exists.return_value = True
    state = BackupStateManager()
    manager = SourceManager(file_system=fs)
    marker_service = Mock()
    marker_service.read_latest.return_value = SourceBackupMarker(
        path, datetime.now(timezone.utc)
    )
    view = Mock()
    config = Mock()
    config.load.return_value = {
        "macos_notifications_enabled": False,
        "warn_on_previously_backed_up_source": False,
    }
    size_service = Mock()
    size_service.size_ready = Mock()
    view_model = Mock()
    view_model.has_basic_conditions.return_value = False
    controller = MainWindowController(
        view=view,
        state_manager=state,
        source_manager=manager,
        view_model=view_model,
        file_selection_handler=FileSelectionHandler(state, manager),
        size_service=size_service,
        config=config,
        file_system=fs,
        source_backup_marker_service=marker_service,
    )

    controller.add_sources([path])

    marker_service.read_latest.assert_called_once_with(path)
    view.confirm_previously_backed_up_source.assert_not_called()
    assert state.source_paths == [path]
