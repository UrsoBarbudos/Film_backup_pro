from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CopyVerificationResult:
    """Доказательство полной проверки, полученное одной операцией копирования."""

    source_path: Path
    destination_path: Path
    source_size: int
    destination_size: int
    source_md5: str
    destination_md5: str
    verification_mode: str
    verified_temporary_file: bool
    temporary_file_synced_and_closed: bool
    atomically_finalized: bool
    run_id: str
    operation_id: str
