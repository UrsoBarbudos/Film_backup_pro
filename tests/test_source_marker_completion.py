from datetime import datetime
from unittest.mock import Mock

from backup_components.orchestrator_services.completion_service import CompletionService


def _orchestrator(*, enabled=True, cancelled=False, failed=0, verification_failed=0):
    config = Mock()
    config.get.side_effect = lambda key, default=None: {
        "mark_source_after_verified_backup": enabled,
    }.get(key, default)
    cancel_token = Mock()
    cancel_token.is_cancelled.return_value = cancelled
    return Mock(
        config=config,
        cancel_token=cancel_token,
        failed_files=failed,
        verification_failed_files=verification_failed,
        verified_files_count=1,
        files_to_verify=[("src", "dst", "name", "Video", 1)],
        source_drives=["/Volumes/CARD/DCIM"],
        destination_root="/Volumes/BACKUP",
        verification_mode="full",
        total_files=1,
        total_bytes=10,
    )


def test_marker_written_after_fully_verified_backup():
    orchestrator = _orchestrator()
    original_end_time = datetime(2026, 7, 28, 12, 0, 0)
    orchestrator.end_time = original_end_time
    warnings = CompletionService().write_source_markers_if_eligible(orchestrator)
    assert warnings == []
    orchestrator.source_backup_marker_service.write_markers.assert_called_once()
    verified_at = orchestrator.source_backup_marker_service.write_markers.call_args.kwargs[
        "verified_at"
    ]
    assert isinstance(verified_at, datetime)
    assert verified_at.tzinfo is not None
    assert orchestrator.end_time == original_end_time


def test_marker_not_written_when_disabled_cancelled_or_verification_failed():
    for orchestrator in (
        _orchestrator(enabled=False),
        _orchestrator(cancelled=True),
        _orchestrator(verification_failed=1, failed=1),
    ):
        assert CompletionService().write_source_markers_if_eligible(orchestrator) == []
        orchestrator.source_backup_marker_service.write_markers.assert_not_called()


def test_read_only_source_is_noncritical_warning():
    orchestrator = _orchestrator()
    orchestrator.source_backup_marker_service.write_markers.side_effect = PermissionError(
        "read-only"
    )
    warnings = CompletionService().write_source_markers_if_eligible(orchestrator)
    assert len(warnings) == 1
    assert "read-only" in warnings[0]
    orchestrator.log_callback.assert_called_once()
