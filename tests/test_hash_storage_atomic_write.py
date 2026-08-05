import os
from pathlib import Path

import pytest

from repositories.file_system_repository import FileSystemRepository
from backup_components.hash_storage import HashStorage
from backup_components.control_tokens import CancelToken
from backup_components.exceptions import BackupCancelledError


class _CancelOnCloseFS:
    """
    Обёртка над реальной ФС: выставляет cancel_event после записи temp-файла.
    Нужна, чтобы детерминированно проверить отмену между write_temp_file и replace.
    """

    def __init__(self, base_fs: FileSystemRepository, cancel_event) -> None:
        self._fs = base_fs
        self._cancel_event = cancel_event

    # --- прокидываем нужные методы интерфейса ---
    def exists(self, path: str) -> bool:  # noqa: D401
        return self._fs.exists(path)

    def isfile(self, path: str) -> bool:
        return self._fs.isfile(path)

    def isdir(self, path: str) -> bool:
        return self._fs.isdir(path)

    def getsize(self, path: str) -> int:
        return self._fs.getsize(path)

    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        return self._fs.makedirs(path, exist_ok=exist_ok)

    def walk(self, path: str):
        return self._fs.walk(path)

    def join(self, *paths: str) -> str:
        return self._fs.join(*paths)

    def basename(self, path: str) -> str:
        return self._fs.basename(path)

    def dirname(self, path: str) -> str:
        return self._fs.dirname(path)

    def relpath(self, path: str, start: str) -> str:
        return self._fs.relpath(path, start)

    def remove(self, path: str) -> None:
        return self._fs.remove(path)

    def getmtime(self, path: str) -> float:
        return self._fs.getmtime(path)

    def copystat(self, src: str, dst: str) -> None:
        return self._fs.copystat(src, dst)

    def copy2(self, src: str, dst: str) -> str:
        return self._fs.copy2(src, dst)

    def disk_usage(self, path: str):
        return self._fs.disk_usage(path)

    def replace(self, src: str, dst: str) -> None:
        return self._fs.replace(src, dst)

    def open(self, path: str, mode: str, *args, **kwargs):
        f = self._fs.open(path, mode, *args, **kwargs)

        # Если это запись temp-файла — после закрытия выставим cancel.
        if "w" in mode and path.endswith(".tmp"):
            cancel_event = self._cancel_event

            class _Wrapped:
                def __init__(self, inner):
                    self._inner = inner

                def __getattr__(self, item):
                    return getattr(self._inner, item)

                def __enter__(self):
                    return self._inner.__enter__()

                def __exit__(self, exc_type, exc, tb):
                    # Выставляем cancel прямо перед выходом из with.
                    cancel_event.set()
                    return self._inner.__exit__(exc_type, exc, tb)

            return _Wrapped(f)

        return f


def _paths(base: Path):
    base_str = str(base)
    return {
        "json": base_str + ".json",
        "gz": base_str + ".json.gz",
        "json_tmp": base_str + ".json.tmp",
        "gz_tmp": base_str + ".json.gz.tmp",
    }


def test_atomic_save_creates_file_and_cleans_tmp(tmp_path: Path) -> None:
    fs = FileSystemRepository()
    base = tmp_path / "hashes"
    hs = HashStorage(file_system=fs, storage_path=str(base))

    hs.set_hash("a", "deadbeef")
    hs.force_save()

    p = _paths(base)
    assert fs.exists(p["gz"]) or fs.exists(p["json"])
    assert not fs.exists(p["json_tmp"])
    assert not fs.exists(p["gz_tmp"])


def test_format_switch_cleanup(tmp_path: Path) -> None:
    fs = FileSystemRepository()
    base = tmp_path / "hashes"
    hs = HashStorage(file_system=fs, storage_path=str(base))

    # Первый save (по умолчанию compression=True)
    hs.set_hash("a", "deadbeef")
    hs.force_save()

    p = _paths(base)
    assert fs.exists(p["gz"])

    # Переключаем формат и сохраняем снова
    hs.use_compression = False
    hs.set_hash("b", "cafebabe")
    hs.force_save()

    assert fs.exists(p["json"])
    assert not fs.exists(p["gz"])


def test_cancel_during_save_does_not_leave_tmp(tmp_path: Path) -> None:
    base_fs = FileSystemRepository()
    base = tmp_path / "hashes"

    # Сначала создаём валидный файл
    hs_ok = HashStorage(file_system=base_fs, storage_path=str(base))
    hs_ok.use_compression = False
    hs_ok.set_hash("a", "deadbeef")
    hs_ok.force_save()
    p = _paths(base)
    assert base_fs.exists(p["json"])

    # Теперь моделируем отмену между записью temp и replace
    import threading

    cancel_event = threading.Event()
    cancel_token = CancelToken(cancel_event)
    fs = _CancelOnCloseFS(base_fs, cancel_event)
    hs = HashStorage(file_system=fs, storage_path=str(base), cancel_token=cancel_token)
    hs.use_compression = False
    hs.set_hash("b", "cafebabe")

    with pytest.raises(BackupCancelledError):
        hs.force_save()

    # temp очищен, основной файл не исчез
    assert not base_fs.exists(p["json_tmp"])
    assert base_fs.exists(p["json"])

