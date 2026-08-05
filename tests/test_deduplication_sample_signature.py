"""Тесты для compute_sample_signature (sample-signature алгоритм)."""

import pytest
from pathlib import Path
from backup_components.deduplication_manager import compute_sample_signature
from repositories.file_system_repository import FileSystemRepository


def test_sample_signature_small_file(tmp_path: Path):
    """Файл меньше 2*chunk читается целиком."""
    fs = FileSystemRepository()
    f = tmp_path / "small.bin"
    f.write_bytes(b"hello world")
    sig = compute_sample_signature(
        file_path=str(f),
        file_system=fs,
        chunk_size_bytes=64,
    )
    assert isinstance(sig, str)
    assert len(sig) == 32  # blake2b digest_size=16 -> hex 32

    sig2 = compute_sample_signature(
        file_path=str(f),
        file_system=fs,
        chunk_size_bytes=64,
    )
    assert sig == sig2


def test_sample_signature_different_content_different_sig(tmp_path: Path):
    fs = FileSystemRepository()
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"aaaa")
    b.write_bytes(b"bbbb")
    sig_a = compute_sample_signature(file_path=str(a), file_system=fs, chunk_size_bytes=2)
    sig_b = compute_sample_signature(file_path=str(b), file_system=fs, chunk_size_bytes=2)
    assert sig_a != sig_b


def test_sample_signature_large_file_first_last_chunk(tmp_path: Path):
    """Файл > 2*chunk: хеш от size + first_chunk + last_chunk."""
    fs = FileSystemRepository()
    f = tmp_path / "large.bin"
    chunk = 4
    data = b"x" * chunk + b"middle" + b"y" * chunk
    f.write_bytes(data)
    sig = compute_sample_signature(file_path=str(f), file_system=fs, chunk_size_bytes=chunk)
    assert isinstance(sig, str)
    assert len(sig) == 32


def test_sample_signature_invalid_chunk_raises(tmp_path: Path):
    fs = FileSystemRepository()
    (tmp_path / "f").write_bytes(b"x")
    with pytest.raises(ValueError, match="chunk_size_bytes must be positive"):
        compute_sample_signature(
            file_path=str(tmp_path / "f"),
            file_system=fs,
            chunk_size_bytes=0,
        )
