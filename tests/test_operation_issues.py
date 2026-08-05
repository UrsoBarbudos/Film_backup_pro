from __future__ import annotations

import errno

import pytest

from backup_components.operation_issue import (
    OperationIssueCode,
    create_operation_issue,
)
from backup_components.operation_results import CopyResult, VerificationResult


@pytest.mark.parametrize(
    ("exc", "stage", "expected"),
    [
        (OSError(errno.ENOSPC, "disk full"), "copy.write_temporary_file", "NO_SPACE_LEFT"),
        (OSError(errno.EACCES, "denied"), "copy.read_source", "PERMISSION_DENIED"),
        (OSError(errno.EPERM, "not permitted"), "copy.write_temporary_file", "PERMISSION_DENIED"),
        (OSError(errno.ENOENT, "missing"), "copy.read_source", "SOURCE_NOT_FOUND"),
        (OSError(errno.EIO, "read error"), "copy.read_source", "READ_FAILED"),
        (OSError(errno.EIO, "write error"), "copy.write_temporary_file", "WRITE_FAILED"),
        (RuntimeError("surprise"), "copy.read_source", "UNKNOWN_ERROR"),
    ],
)
def test_exception_classifier_uses_errno_and_stage(exc, stage, expected):
    issue = create_operation_issue(
        exc,
        stage=stage,
        source_path="/Volumes/CARD/clip.mov",
        destination_path="/Volumes/BACKUP/clip.mov",
        file_name="clip.mov",
    )

    assert issue.code == expected
    assert issue.technical_message == str(exc)
    assert issue.timestamp is not None


def test_result_models_reject_inconsistent_states():
    issue = create_operation_issue(RuntimeError("broken"), stage="copy.read_source")

    with pytest.raises(ValueError):
        CopyResult(success=True, copied_size=1, issue=issue)
    with pytest.raises(ValueError):
        CopyResult(success=False, copied_size=0)
    with pytest.raises(ValueError):
        VerificationResult(success=True, issue=issue)
    with pytest.raises(ValueError):
        VerificationResult(success=False)


def test_successful_results_do_not_contain_issue():
    assert CopyResult(success=True, copied_size=12).issue is None
    assert VerificationResult(success=True).issue is None
