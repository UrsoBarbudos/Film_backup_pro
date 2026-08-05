"""Тесты для utils: format_size, safe_add_bytes."""

import sys
import pytest
from utils import format_size, safe_add_bytes


class TestFormatSize:
    def test_zero(self):
        assert format_size(0) == "0 B"

    def test_bytes(self):
        assert format_size(500) == "500 B"
        assert format_size(999) == "999 B"

    def test_kb(self):
        assert format_size(1000) == "1 KB"
        assert format_size(1500) == "1.50 KB"  # код даёт .2f → 1.50, .00 убирается только для целых
        assert format_size(999_999) == "1000 KB"

    def test_mb(self):
        assert format_size(1_000_000) == "1 MB"
        assert format_size(1_500_000) == "1.50 MB"
        assert format_size(999_999_999) == "1000 MB"

    def test_gb(self):
        assert format_size(1_000_000_000) == "1 GB"
        assert format_size(24_000_000_000) == "24 GB"
        assert format_size(1_500_000_000) == "1.50 GB"

    def test_negative_returns_zero_b(self):
        assert format_size(-1) == "0 B"


class TestSafeAddBytes:
    def test_normal_addition(self):
        assert safe_add_bytes(100, 200) == 300
        assert safe_add_bytes(0, 0) == 0

    def test_maxsize_plus_one(self):
        # В Python 3 int не переполняется; функция может вернуть сумму или sys.maxsize
        a = sys.maxsize
        result = safe_add_bytes(a, 1)
        assert result >= sys.maxsize

    def test_large_positive_sum(self):
        a = sys.maxsize // 2
        b = sys.maxsize // 2
        result = safe_add_bytes(a, b)
        assert result == a + b
