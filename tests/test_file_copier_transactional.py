from pathlib import Path
import threading

import pytest

from backup_components.control_tokens import CancelToken
from backup_components.exceptions import BackupCancelledError
from backup_components.file_copier import FileCopier
from backup_components.copy_verification_result import CopyVerificationResult
from backup_components.file_verifier import FileVerifier
from repositories.file_system_repository import FileSystemRepository


def _partial_files(directory: Path) -> list[Path]:
    return list(directory.glob(".*.partial"))


def test_replaces_existing_file_only_after_verified_temp_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"new footage")
    destination.write_bytes(b"known good backup")

    copier = FileCopier(file_system=FileSystemRepository(), verification_mode="full")

    result = copier.copy_file(
        str(source), str(destination)
    )

    assert result.success is True
    assert result.issue is None
    assert result.copied_size == source.stat().st_size
    assert isinstance(result.verification, CopyVerificationResult)
    assert destination.read_bytes() == source.read_bytes()
    assert _partial_files(tmp_path) == []


def test_full_mode_reads_destination_once_and_verifier_reuses_result(
    tmp_path: Path,
) -> None:
    class CountingFileSystem(FileSystemRepository):
        def __init__(self) -> None:
            self.full_reads = 0

        def open(self, path: str, mode: str = "r", *args, **kwargs):
            file_object = super().open(path, mode, *args, **kwargs)
            if mode == "rb" and path != str(source):
                self.full_reads += 1
            return file_object

    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"large-video-block" * 1024)
    fs = CountingFileSystem()
    run_id = "current-run"
    copier = FileCopier(
        file_system=fs,
        verification_mode="full",
        verification_run_id=run_id,
    )
    verifier = FileVerifier(
        file_system=fs,
        verification_mode="full",
        verification_run_id=run_id,
    )

    copy_result = copier.copy_file(str(source), str(destination))
    assert copy_result.success is True
    assert fs.full_reads == 1
    assert copier.verification_read_bytes == source.stat().st_size

    verification_result = verifier.verify_file(
        str(source), str(destination), copy_result.verification
    )

    assert verification_result.success is True
    assert verification_result.issue is None
    assert fs.full_reads == 1
    assert verifier.verification_read_bytes == 0
    assert copier.verification_read_bytes + verifier.verification_read_bytes == source.stat().st_size


def test_final_destination_size_is_checked_after_replace(tmp_path: Path) -> None:
    class RecordingFileSystem(FileSystemRepository):
        def __init__(self) -> None:
            self.replaced = False
            self.size_checked_after_replace = False

        def replace(self, source: str, destination: str) -> None:
            super().replace(source, destination)
            self.replaced = True

        def getsize(self, path: str) -> int:
            if self.replaced and path == str(destination):
                self.size_checked_after_replace = True
            return super().getsize(path)

    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"footage")
    fs = RecordingFileSystem()
    copier = FileCopier(file_system=fs, verification_mode="full")

    result = copier.copy_file(str(source), str(destination))

    assert result.success is True
    assert result.verification is not None
    assert fs.size_checked_after_replace is True


def test_copy_failure_preserves_existing_destination_and_removes_partial(
    tmp_path: Path,
) -> None:
    class FailingSyncFileSystem(FileSystemRepository):
        def fsync_file(self, file_object) -> None:
            super().fsync_file(file_object)
            raise OSError("simulated fsync failure")

    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"new footage")
    destination.write_bytes(b"known good backup")

    copier = FileCopier(file_system=FailingSyncFileSystem())

    result = copier.copy_file(str(source), str(destination))

    assert result.success is False
    assert result.issue is not None
    assert result.issue.code == "FSYNC_FAILED"
    assert destination.read_bytes() == b"known good backup"
    assert _partial_files(tmp_path) == []


def test_hash_mismatch_preserves_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"new footage")
    destination.write_bytes(b"known good backup")
    copier = FileCopier(file_system=FileSystemRepository(), verification_mode="full")
    copier._calculate_md5 = lambda _path: "wrong hash"  # type: ignore[method-assign]

    result = copier.copy_file(str(source), str(destination))

    assert result.success is False
    assert result.issue is not None
    assert result.issue.code == "HASH_MISMATCH"
    assert destination.read_bytes() == b"known good backup"
    assert _partial_files(tmp_path) == []


def test_cancellation_preserves_existing_destination_and_removes_partial(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"new footage")
    destination.write_bytes(b"known good backup")
    token = CancelToken(threading.Event())
    copier = FileCopier(file_system=FileSystemRepository(), cancel_token=token)
    original_copy = copier._copy_with_shutil

    def copy_then_cancel(source_path: str, temp_path: str):
        result = original_copy(source_path, temp_path)
        token.cancel()
        return result

    copier._copy_with_shutil = copy_then_cancel  # type: ignore[method-assign]

    with pytest.raises(BackupCancelledError):
        copier.copy_file(str(source), str(destination))

    assert destination.read_bytes() == b"known good backup"
    assert _partial_files(tmp_path) == []


def test_source_changed_during_copy_is_not_published(tmp_path: Path) -> None:
    class MutatingSourceFileSystem(FileSystemRepository):
        def copystat(self, src: str, dst: str) -> None:
            super().copystat(src, dst)
            original_size = Path(src).stat().st_size
            Path(src).write_bytes(b"x" * original_size)

    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"original footage")
    destination.write_bytes(b"known good backup")
    copier = FileCopier(
        file_system=MutatingSourceFileSystem(),
        verification_mode="full",
    )

    result = copier.copy_file(str(source), str(destination))

    assert result.success is False
    assert result.copied_size == 0
    assert result.verification is None
    assert result.issue is not None
    assert result.issue.code == "SOURCE_CHANGED"
    assert destination.read_bytes() == b"known good backup"
    assert _partial_files(tmp_path) == []


@pytest.mark.parametrize("failure", ["temporary_read", "replace"])
def test_full_verification_failure_does_not_create_result_or_replace_old_file(
    tmp_path: Path, failure: str
) -> None:
    class FailingFileSystem(FileSystemRepository):
        def open(self, path: str, mode: str = "r", *args, **kwargs):
            if failure == "temporary_read" and mode == "rb" and path.endswith(".partial"):
                raise OSError("simulated temporary read failure")
            return super().open(path, mode, *args, **kwargs)

        def replace(self, source: str, destination: str) -> None:
            if failure == "replace":
                raise OSError("simulated replace failure")
            super().replace(source, destination)

    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"new footage")
    destination.write_bytes(b"known good backup")
    copier = FileCopier(file_system=FailingFileSystem(), verification_mode="full")

    result = copier.copy_file(str(source), str(destination))

    assert result.success is False
    assert result.copied_size == 0
    assert result.verification is None
    assert result.issue is not None
    assert result.issue.code == (
        "HASH_CALCULATION_FAILED" if failure == "temporary_read" else "ATOMIC_REPLACE_FAILED"
    )
    assert destination.read_bytes() == b"known good backup"
    assert _partial_files(tmp_path) == []


def test_final_size_mismatch_invalidates_result(tmp_path: Path) -> None:
    class WrongFinalSizeFileSystem(FileSystemRepository):
        def __init__(self) -> None:
            self.finalized_destination: str | None = None

        def replace(self, source: str, destination: str) -> None:
            super().replace(source, destination)
            self.finalized_destination = destination

        def getsize(self, path: str) -> int:
            size = super().getsize(path)
            if path == self.finalized_destination:
                return size + 1
            return size

    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"footage")
    copier = FileCopier(
        file_system=WrongFinalSizeFileSystem(), verification_mode="full"
    )

    result = copier.copy_file(str(source), str(destination))

    assert result.success is False
    assert result.copied_size == 0
    assert result.verification is None
    assert result.issue is not None
    assert result.issue.code == "FILE_SIZE_MISMATCH"


def test_fast_mode_does_not_read_destination_for_full_md5(tmp_path: Path) -> None:
    source = tmp_path / "source.mov"
    destination = tmp_path / "destination.mov"
    source.write_bytes(b"footage")
    copier = FileCopier(
        file_system=FileSystemRepository(), verification_mode="fast"
    )

    result = copier.copy_file(str(source), str(destination))

    assert result.success is True
    assert result.verification is None
    assert result.issue is None
    assert copier.verification_read_bytes == 0
