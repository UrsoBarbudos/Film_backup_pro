"""Тесты для RetryHandler и is_temporary_error."""

import errno
import pytest
from backup_components.exceptions import is_temporary_error
from backup_components.retry_handler import RetryHandler


class TestIsTemporaryError:
    def test_permission_error_is_temporary(self):
        assert is_temporary_error(PermissionError("denied")) is True

    def test_oserror_eagain_is_temporary(self):
        e = OSError()
        e.errno = errno.EAGAIN
        assert is_temporary_error(e) is True

    def test_oserror_eintr_is_temporary(self):
        e = OSError()
        e.errno = errno.EINTR
        assert is_temporary_error(e) is True

    def test_oserror_ebusy_is_temporary(self):
        e = OSError()
        e.errno = errno.EBUSY
        assert is_temporary_error(e) is True

    def test_oserror_enoent_not_temporary(self):
        e = OSError()
        e.errno = errno.ENOENT
        assert is_temporary_error(e) is False

    def test_other_exception_not_temporary(self):
        assert is_temporary_error(ValueError("x")) is False
        assert is_temporary_error(FileNotFoundError()) is False


class TestRetryHandler:
    def test_success_first_try(self):
        handler = RetryHandler(max_attempts=3, delay=0.01)
        result = handler.retry_on_temporary_error(lambda: 42)
        assert result == 42

    def test_success_after_retry(self):
        calls = []
        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise PermissionError("temp")
            return "ok"
        handler = RetryHandler(max_attempts=3, delay=0.01)
        result = handler.retry_on_temporary_error(flaky)
        assert result == "ok"
        assert len(calls) == 2

    def test_non_temporary_raises_immediately(self):
        handler = RetryHandler(max_attempts=3, delay=0.01)
        with pytest.raises(ValueError):
            handler.retry_on_temporary_error(lambda: (_ for _ in ()).throw(ValueError("permanent")))
        # Не должно быть повторных попыток

    def test_exhausted_retries_raises(self):
        handler = RetryHandler(max_attempts=2, delay=0.01)
        with pytest.raises(PermissionError):
            handler.retry_on_temporary_error(lambda: (_ for _ in ()).throw(PermissionError("always")))
