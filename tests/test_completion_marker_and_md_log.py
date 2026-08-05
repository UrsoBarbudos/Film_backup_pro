from datetime import datetime
from unittest.mock import Mock

from backup_components.orchestrator_services.completion_service import CompletionService


def test_marker_timestamp_does_not_break_destination_md_log(tmp_path):
    marker_service = Mock()
    config = Mock()
    config.get.side_effect = lambda key, default=None: {
        "mark_source_after_verified_backup": True,
    }.get(key, default)
    file_system = Mock()
    file_system.join.side_effect = lambda *parts: str(tmp_path.joinpath(*parts[1:]))
    orchestrator = Mock(
        config=config,
        source_backup_marker_service=marker_service,
        source_drives=["/Volumes/CARD/DCIM"],
        cancel_token=Mock(),
        failed_files=0,
        verification_failed_files=0,
        verified_files_count=1,
        files_to_verify=[("src", "dst", "clip.mov", "Video", 10)],
        destination_root=str(tmp_path),
        verification_mode="full",
        total_files=1,
        total_bytes=10,
        copied_bytes=10,
        successful_files=1,
        start_time=datetime(2026, 7, 28, 10, 0, 0),
        end_time=datetime(2026, 7, 28, 10, 1, 0),
        create_md_log=True,
        backup_logger=Mock(),
        file_system=file_system,
        copied_files={},
        operation_issues=[],
    )
    orchestrator.cancel_token.is_cancelled.return_value = False
    orchestrator.backup_logger.create_md_log_file.return_value = str(
        tmp_path / "backup_log.md"
    )

    service = CompletionService()
    assert service.write_source_markers_if_eligible(orchestrator) == []
    service.create_md_log_if_needed(orchestrator)

    marker_service.write_markers.assert_called_once()
    orchestrator.backup_logger.create_md_log_file.assert_called_once()
    call = orchestrator.backup_logger.create_md_log_file.call_args.kwargs
    assert call["end_time"] - call["start_time"] == datetime(
        2026, 7, 28, 10, 1, 0
    ) - datetime(2026, 7, 28, 10, 0, 0)
