from datetime import datetime
from types import SimpleNamespace

from backup_components.orchestrator_services.completion_service import CompletionService


def _orchestrator(**overrides):
    values = {
        "total_files": 3,
        "successful_files": 2,
        "failed_files": 1,
        "start_time": datetime(2026, 7, 27, 10, 0, 0),
        "end_time": datetime(2026, 7, 27, 10, 1, 0),
        "total_bytes": 300,
        "copied_bytes": 200,
        "destination_root": "/tmp/destination",
        "source_drives": ["/Volumes/CARD_A"],
        "copied_files": {
            "Video": [{"size": 100}, {"size": 100}],
            "Audio": [],
        },
        "operation_issues": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_completion_stats_has_one_full_schema_for_success():
    stats = CompletionService().prepare_completion_stats(_orchestrator())

    assert stats["start_time"] == "2026-07-27T10:00:00"
    assert stats["end_time"] == "2026-07-27T10:01:00"
    assert stats["source_drives"] == ["/Volumes/CARD_A"]
    assert stats["category_stats"]["Video"] == {"count": 2, "total_size": 200}
    assert stats["category_stats"]["Photo"] == {"count": 0, "total_size": 0}


def test_completion_stats_uses_same_schema_when_run_is_cancelled():
    stats = CompletionService().prepare_completion_stats(
        _orchestrator(end_time=None, destination_root="", copied_files={})
    )

    assert set(stats) == {
        "total_files",
        "successful_files",
        "failed_files",
        "verification_failed_files",
        "verified_files",
        "unverified_files",
        "start_time",
        "end_time",
        "total_bytes",
        "copied_bytes",
        "verification_read_bytes",
        "destination_path",
        "source_drives",
        "category_stats",
        "issues",
    }
    assert stats["end_time"] is not None
    assert stats["destination_path"] == ""


def test_completion_stats_safe_wrapper_does_not_mask_original_failure():
    broken = SimpleNamespace(
        copied_files={"Video": [None]},
        source_drives=[],
    )

    assert CompletionService().prepare_completion_stats_safely(broken) is None
