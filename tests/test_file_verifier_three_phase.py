"""
Тесты для трёхфазной верификации файлов (Level A: размер → Level B: sample → Level C: MD5)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backup_components.file_verifier import FileVerifier
from backup_components.file_copier import FileCopier
from repositories import FileSystemRepository


def _issue_text(result) -> str:
    if result.issue is None:
        return ""
    return " ".join(
        value for value in (result.issue.message, result.issue.technical_message) if value
    )


@pytest.fixture
def fs():
    """Фикстура для файловой системы"""
    return FileSystemRepository()


@pytest.fixture
def verifier(fs):
    """Фикстура для FileVerifier в режиме full"""
    return FileVerifier(
        file_system=fs,
        verification_mode='full',
        hash_storage=None,
    )


def test_level_a_size_mismatch(tmp_path: Path, verifier: FileVerifier, fs):
    """Тест Level A: обнаружение ошибки при несовпадении размеров"""
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    
    # Создаём файлы разного размера
    src_file.write_bytes(b"source content" * 100)
    dst_file.write_bytes(b"dest content")
    
    result = verifier.verify_file(str(src_file), str(dst_file))
    error_msg = _issue_text(result)
    
    assert result.success is False
    assert result.issue.code == "FILE_SIZE_MISMATCH"
    assert "Размер копии не совпадает" in error_msg
    assert "source=" in error_msg
    assert "destination=" in error_msg


def test_level_b_sample_mismatch(tmp_path: Path, verifier: FileVerifier, fs):
    """Тест Level B: обнаружение ошибки при несовпадении sample_signature"""
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    
    # Создаём файлы одинакового размера, но с разным содержимым
    # Используем достаточно большой файл, чтобы sample читал только начало и конец
    src_content = b"start" + b"x" * (2 * 1024 * 1024) + b"end"
    dst_content = b"start" + b"y" * (2 * 1024 * 1024) + b"end"
    
    src_file.write_bytes(src_content)
    dst_file.write_bytes(dst_content)
    
    # Убеждаемся, что размеры совпадают
    assert len(src_content) == len(dst_content)
    
    result = verifier.verify_file(str(src_file), str(dst_file))
    error_msg = _issue_text(result)
    
    assert result.success is False
    assert result.issue.code == "HASH_MISMATCH"
    assert "Контрольная выборка" in error_msg


def test_level_c_md5_mismatch(tmp_path: Path, verifier: FileVerifier, fs):
    """Тест Level C: обнаружение ошибки при несовпадении MD5"""
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    
    # Создаём файлы одинакового размера, но с разным содержимым
    # Используем одинаковую длину строк для одинакового размера
    content_size = 10000
    src_content = (b"source content" * (content_size // len(b"source content") + 1))[:content_size]
    dst_content = (b"dest content" * (content_size // len(b"dest content") + 1))[:content_size]
    
    # Убеждаемся, что размеры совпадают
    assert len(src_content) == len(dst_content) == content_size
    
    src_file.write_bytes(src_content)
    dst_file.write_bytes(dst_content)
    
    result = verifier.verify_file(str(src_file), str(dst_file))
    error_msg = _issue_text(result)
    
    # Ошибка должна быть обнаружена на Level B (sample) или Level C (MD5)
    assert result.success is False
    assert result.issue.code == "HASH_MISMATCH"
    assert "не совпадает" in error_msg


def test_successful_verification_all_levels(tmp_path: Path, verifier: FileVerifier, fs):
    """Тест успешной проверки: все 3 уровня проходят"""
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    
    # Создаём идентичные файлы
    content = b"test content" * 1000
    src_file.write_bytes(content)
    dst_file.write_bytes(content)
    
    result = verifier.verify_file(str(src_file), str(dst_file))
    
    assert result.success is True
    assert result.issue is None


def test_small_file_verification(tmp_path: Path, verifier: FileVerifier, fs):
    """Тест проверки маленького файла (<2MB, sample читает весь файл)"""
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    
    # Маленький файл
    content = b"small file content"
    src_file.write_bytes(content)
    dst_file.write_bytes(content)
    
    result = verifier.verify_file(str(src_file), str(dst_file))
    
    assert result.success is True
    assert result.issue is None


def test_large_file_with_error(tmp_path: Path, verifier: FileVerifier, fs):
    """Тест проверки большого файла с ошибкой (должен быстро обнаружить на Level A или B)"""
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    
    # Создаём большой файл (10MB)
    large_content = b"x" * (10 * 1024 * 1024)
    src_file.write_bytes(large_content)
    
    # Создаём файл с ошибкой в начале (разный размер)
    dst_file.write_bytes(b"error")
    
    result = verifier.verify_file(str(src_file), str(dst_file))
    
    assert result.success is False
    # Должна быть ошибка на Level A (размер)
    assert result.issue.code == "FILE_SIZE_MISMATCH"


def test_verification_with_hash_storage(tmp_path: Path, fs):
    """Тест проверки с использованием HashStorage для кэширования"""
    from backup_components.hash_storage import HashStorage
    
    # Направляем app data dir в tmp
    os.environ["FILM_BACKUP_PRO_APP_DATA_DIR"] = str(tmp_path / "app_data")
    
    hash_storage = HashStorage(file_system=fs)
    verifier = FileVerifier(
        file_system=fs,
        verification_mode='full',
        hash_storage=hash_storage,
    )
    
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    
    content = b"test content for caching"
    src_file.write_bytes(content)
    dst_file.write_bytes(content)
    
    # Первая проверка - вычисляет и кэширует
    result1 = verifier.verify_file(str(src_file), str(dst_file))
    assert result1.success is True
    
    # Вторая проверка может использовать кэш источника, но назначение читает заново.
    result2 = verifier.verify_file(str(src_file), str(dst_file))
    assert result2.success is True
    assert verifier.verification_read_bytes == 2 * len(content)
    
    # Проверяем, что хеши были сохранены
    assert hash_storage.get_hash(str(src_file)) is not None
    assert hash_storage.get_hash(str(dst_file)) is not None


def test_verification_cancel_token(tmp_path: Path, fs):
    """Тест обработки отмены проверки"""
    from backup_components.control_tokens import CancelToken
    from backup_components.exceptions import BackupCancelledError
    import threading

    cancel_token = CancelToken(threading.Event())

    verifier = FileVerifier(
        file_system=fs,
        verification_mode='full',
        cancel_token=cancel_token,
    )

    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"

    # Создаём большой файл для проверки отмены во время чтения
    large_content = b"x" * (5 * 1024 * 1024)  # 5MB
    src_file.write_bytes(large_content)
    dst_file.write_bytes(large_content)

    cancel_token.cancel()

    # Проверка должна выбросить BackupCancelledError
    with pytest.raises(BackupCancelledError):
        verifier.verify_file(str(src_file), str(dst_file))


def test_without_trusted_result_full_md5_is_computed(tmp_path: Path, fs, monkeypatch):
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    src_file.write_bytes(b"same content")
    dst_file.write_bytes(b"same content")
    verifier = FileVerifier(file_system=fs, verification_mode="full")
    md5_paths: list[str] = []

    from backup_components import file_verifier as verifier_module

    original = verifier_module.get_or_compute_md5

    def recording_md5(**kwargs):
        md5_paths.append(kwargs["file_path"])
        return original(**kwargs)

    monkeypatch.setattr(verifier_module, "get_or_compute_md5", recording_md5)

    result = verifier.verify_file(str(src_file), str(dst_file))

    assert result.success is True
    assert md5_paths == [str(src_file)]
    assert verifier.verification_read_bytes == dst_file.stat().st_size


def test_result_from_other_run_or_path_is_not_accepted(
    tmp_path: Path, fs, monkeypatch
):
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    other_dst = tmp_path / "other.bin"
    src_file.write_bytes(b"same content")
    run_id = "copy-run"
    copier = FileCopier(
        file_system=fs,
        verification_mode="full",
        verification_run_id=run_id,
    )
    copy_result = copier.copy_file(str(src_file), str(dst_file))
    assert copy_result.success is True
    other_dst.write_bytes(src_file.read_bytes())

    from backup_components import file_verifier as verifier_module

    calls = 0
    original = verifier_module.get_or_compute_md5

    def recording_md5(**kwargs):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    monkeypatch.setattr(verifier_module, "get_or_compute_md5", recording_md5)
    wrong_run_verifier = FileVerifier(
        file_system=fs,
        verification_mode="full",
        verification_run_id="other-run",
    )
    assert wrong_run_verifier.verify_file(
        str(src_file), str(dst_file), copy_result.verification
    ).success is True
    assert calls == 1
    assert wrong_run_verifier.verification_read_bytes == dst_file.stat().st_size

    calls = 0
    matching_run_verifier = FileVerifier(
        file_system=fs,
        verification_mode="full",
        verification_run_id=run_id,
    )
    assert matching_run_verifier.verify_file(
        str(src_file), str(other_dst), copy_result.verification
    ).success is True
    assert calls == 1
    assert matching_run_verifier.verification_read_bytes == other_dst.stat().st_size


def test_result_for_other_source_is_not_accepted(tmp_path: Path, fs):
    src_file = tmp_path / "source.bin"
    other_src = tmp_path / "other-source.bin"
    dst_file = tmp_path / "dest.bin"
    src_file.write_bytes(b"same content")
    other_src.write_bytes(b"same content")
    run_id = "copy-run"
    copier = FileCopier(
        file_system=fs,
        verification_mode="full",
        verification_run_id=run_id,
    )
    copy_result = copier.copy_file(str(src_file), str(dst_file))
    verifier = FileVerifier(
        file_system=fs,
        verification_mode="full",
        verification_run_id=run_id,
    )

    assert verifier.verify_file(
        str(other_src), str(dst_file), copy_result.verification
    ).success is True
    assert verifier.verification_read_bytes == dst_file.stat().st_size


def test_copy_result_is_consumed_only_once(tmp_path: Path, fs, monkeypatch):
    src_file = tmp_path / "source.bin"
    dst_file = tmp_path / "dest.bin"
    src_file.write_bytes(b"same content")
    run_id = "one-run"
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
    copy_result = copier.copy_file(str(src_file), str(dst_file))
    assert verifier.verify_file(
        str(src_file), str(dst_file), copy_result.verification
    ).success is True

    from backup_components import file_verifier as verifier_module

    calls = 0
    original = verifier_module.get_or_compute_md5

    def recording_md5(**kwargs):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    monkeypatch.setattr(verifier_module, "get_or_compute_md5", recording_md5)
    assert verifier.verify_file(
        str(src_file), str(dst_file), copy_result.verification
    ).success is True
    assert calls == 1
    assert verifier.verification_read_bytes == dst_file.stat().st_size
