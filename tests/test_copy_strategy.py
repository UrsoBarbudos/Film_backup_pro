"""Тесты для стратегии копирования (get_copy_method)."""

import pytest
from backup_components.copy_strategy import (
    get_copy_method,
    CopyMethod,
    LARGE_FILE_THRESHOLD_BYTES,
)


def test_small_file_uses_shutil():
    assert get_copy_method(0) == CopyMethod.SHUTIL
    assert get_copy_method(1) == CopyMethod.SHUTIL
    assert get_copy_method(50 * 1024 * 1024) == CopyMethod.SHUTIL
    assert get_copy_method(99 * 1024 * 1024) == CopyMethod.SHUTIL


def test_at_threshold_uses_block():
    assert get_copy_method(LARGE_FILE_THRESHOLD_BYTES) == CopyMethod.BLOCK


def test_large_file_uses_block():
    assert get_copy_method(100 * 1024 * 1024) == CopyMethod.BLOCK
    assert get_copy_method(100 * 1024 * 1024 + 1) == CopyMethod.BLOCK
    assert get_copy_method(10 * 1024 * 1024 * 1024) == CopyMethod.BLOCK


def test_threshold_constant():
    assert LARGE_FILE_THRESHOLD_BYTES == 100 * 1024 * 1024
