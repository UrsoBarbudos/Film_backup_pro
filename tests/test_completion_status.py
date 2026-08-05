from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backup_components.completion_status import (
    BackupCompletionStatus,
    determine_completion_status,
)
from backup_components.orchestrator_services.completion_service import CompletionService
from backup_components.orchestrator_services.verification_service import VerificationService
from backup_components.operation_issue import OperationIssueCode, create_message_issue
from backup_components.operation_results import CopyResult, VerificationResult


def _mismatch(message="mismatch"):
    return create_message_issue(
        stage="verification.hash",
        code=OperationIssueCode.HASH_MISMATCH,
        message=message,
        source_path="src",
        destination_path="dst",
        file_name="clip.mov",
    )


@pytest.mark.parametrize(
    ("stats", "expected"),
    [
        (
            {
                "failed_files": 0,
                "verification_failed_files": 0,
                "unverified_files": 0,
            },
            BackupCompletionStatus.SUCCESS,
        ),
        (
            {
                "failed_files": 0,
                "verification_failed_files": 0,
                "unverified_files": 1,
            },
            BackupCompletionStatus.WARNING,
        ),
        (
            {
                "failed_files": 1,
                "verification_failed_files": 0,
                "unverified_files": 0,
            },
            BackupCompletionStatus.FAILED,
        ),
        (
            {
                "failed_files": 0,
                "verification_failed_files": 1,
                "unverified_files": 0,
            },
            BackupCompletionStatus.FAILED,
        ),
    ],
)
def test_determine_completion_status(stats, expected):
    assert determine_completion_status(stats) is expected


def test_cancelled_status_has_priority():
    assert determine_completion_status({}, was_cancelled=True) is BackupCompletionStatus.CANCELLED


def test_completion_signal_never_reports_success_for_failed_file():
    signals = Mock()
    orchestrator = SimpleNamespace(signals=signals)
    stats = {
        "failed_files": 1,
        "verification_failed_files": 0,
        "unverified_files": 0,
    }

    CompletionService().emit_completion_signal(orchestrator, stats)

    signals.finished.emit.assert_called_once_with(
        "failed", "Резервное копирование завершено с ошибками", stats
    )


def test_verification_retry_success_restores_fully_verified_result():
    orchestrator = Mock()
    orchestrator.files_to_verify = [("src", "dst", "clip.mov", "Video", 10)]
    orchestrator.verified_files_set = set()
    orchestrator.successful_files = 1
    orchestrator.failed_files = 0
    orchestrator.file_verifier.verify_file.side_effect = [
        VerificationResult(success=False, issue=_mismatch()),
        VerificationResult(success=True),
    ]
    orchestrator.verification_action_callback.return_value = "recopy"
    orchestrator.file_copier.copy_file.return_value = CopyResult(
        success=True, copied_size=10
    )
    orchestrator.cancel_token.is_cancelled.return_value = False

    VerificationService().verify_all_files(orchestrator)

    assert orchestrator.verified_files_count == 1
    assert orchestrator.verification_failed_files == 0
    assert orchestrator.failed_files == 0


def test_verification_skip_is_a_failure():
    orchestrator = Mock()
    orchestrator.files_to_verify = [("src", "dst", "clip.mov", "Video", 10)]
    orchestrator.verified_files_set = set()
    orchestrator.successful_files = 1
    orchestrator.failed_files = 0
    orchestrator.file_verifier.verify_file.return_value = VerificationResult(
        success=False, issue=_mismatch()
    )
    orchestrator.verification_action_callback.return_value = "skip"

    VerificationService().verify_all_files(orchestrator)

    assert orchestrator.verified_files_count == 0
    assert orchestrator.verification_failed_files == 1
    assert orchestrator.failed_files == 1
    orchestrator.file_system.remove.assert_called_once_with("dst")
    callback_args = orchestrator.verification_action_callback.call_args.args
    assert callback_args[:2] == ("src", "dst")
    assert "mismatch" in callback_args[2]
    orchestrator.record_issue.assert_called_once()


def test_failed_retry_asks_again_and_can_be_skipped():
    orchestrator = Mock()
    orchestrator.files_to_verify = [("src", "dst", "clip.mov", "Video", 10)]
    orchestrator.verified_files_set = set()
    orchestrator.successful_files = 1
    orchestrator.failed_files = 0
    orchestrator.file_verifier.verify_file.side_effect = [
        VerificationResult(success=False, issue=_mismatch()),
        VerificationResult(success=False, issue=_mismatch("mismatch again")),
    ]
    orchestrator.verification_action_callback.side_effect = ["recopy", "skip"]
    orchestrator.file_copier.copy_file.return_value = CopyResult(
        success=True, copied_size=10
    )

    VerificationService().verify_all_files(orchestrator)

    assert orchestrator.verification_action_callback.call_count == 2
    assert orchestrator.verification_failed_files == 1
