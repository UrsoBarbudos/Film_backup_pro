"""
Дедупликация: sample_signature и MD5 для верификации и кэширования.
Индекс назначения по размеру и A/B/C дедупликация удалены; конфликты решаются диалогом «Файл уже существует».
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional, TYPE_CHECKING

from interfaces import IFileSystemInterface

if TYPE_CHECKING:
    from .control_tokens import CancelToken
    from .hash_storage import HashStorage

logger = logging.getLogger(__name__)


def compute_sample_signature(
    *,
    file_path: str,
    file_system: IFileSystemInterface,
    chunk_size_bytes: int,
) -> str:
    """
    Вычисляет sample_signature для файла: hash(size || first_chunk || last_chunk).

    Для маленьких файлов (<2*chunk_size) читаем файл целиком один раз.
    Хеш: blake2b (быстро, встроенно), digest_size=16 (достаточно для сигнатуры).
    """
    chunk = int(chunk_size_bytes)
    if chunk <= 0:
        raise ValueError("chunk_size_bytes must be positive")

    size = int(file_system.getsize(file_path))
    h = hashlib.blake2b(digest_size=16)
    h.update(size.to_bytes(8, byteorder="little", signed=False))

    with file_system.open(file_path, "rb") as f:
        if size <= 2 * chunk:
            data = f.read()
            h.update(data)
            return h.hexdigest()

        first = f.read(chunk)
        h.update(first)
        try:
            f.seek(size - chunk)
        except Exception:
            # best-effort: если seek недоступен (редко), дочитаем до конца потоково
            remaining = f.read()
            h.update(remaining[-chunk:] if len(remaining) > chunk else remaining)
            return h.hexdigest()

        last = f.read(chunk)
        h.update(last)
        return h.hexdigest()


def get_or_compute_sample_signature(
    *,
    file_path: str,
    file_system: IFileSystemInterface,
    chunk_size_bytes: int,
    hash_storage: Optional["HashStorage"] = None,
) -> str:
    """
    Возвращает sample_signature из кэша (HashStorage) или вычисляет и сохраняет.
    """
    if hash_storage is not None:
        cached = hash_storage.get_sample_signature(file_path, chunk_size_bytes=int(chunk_size_bytes))
        if cached:
            return cached

    sig = compute_sample_signature(
        file_path=file_path,
        file_system=file_system,
        chunk_size_bytes=int(chunk_size_bytes),
    )
    if hash_storage is not None:
        try:
            hash_storage.set_sample_signature(
                file_path=file_path,
                sample_sig=sig,
                chunk_size_bytes=int(chunk_size_bytes),
            )
        except Exception as exc:  # noqa: BLE001 - best-effort caching
            logger.debug("Failed to cache sample_signature for %s: %s", file_path, exc)
    return sig


def compute_md5(
    *,
    file_path: str,
    file_system: IFileSystemInterface,
    cancel_token: Optional["CancelToken"] = None,
) -> str:
    """
    Вычисляет MD5 файла (адаптивные размеры блоков как в копировании/верификации).
    """
    size = int(file_system.getsize(file_path))
    if size > 50 * 1024 * 1024 * 1024:  # >50 GB
        block_size = 20 * 1024 * 1024
    elif size > 10 * 1024 * 1024 * 1024:  # >10 GB
        block_size = 15 * 1024 * 1024
    else:
        block_size = 10 * 1024 * 1024

    if cancel_token is not None:
        cancel_token.raise_if_cancelled("Проверка отменена пользователем")

    h = hashlib.md5()
    with file_system.open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            if cancel_token is not None:
                cancel_token.raise_if_cancelled("Проверка отменена пользователем")
            h.update(chunk)
    return h.hexdigest()


def get_or_compute_md5(
    *,
    file_path: str,
    file_system: IFileSystemInterface,
    hash_storage: Optional["HashStorage"] = None,
    cancel_token: Optional["CancelToken"] = None,
) -> str:
    """
    Берёт MD5 из HashStorage или вычисляет и сохраняет.
    """
    if hash_storage is not None:
        cached = hash_storage.get_hash(file_path)
        if cached:
            return cached

    md5 = compute_md5(file_path=file_path, file_system=file_system, cancel_token=cancel_token)
    if hash_storage is not None:
        try:
            modified_time = None
            try:
                import datetime as _dt

                ts = file_system.getmtime(file_path)
                modified_time = _dt.datetime.fromtimestamp(ts).isoformat()
            except Exception:
                modified_time = None

            hash_storage.set_hash(
                file_path=file_path,
                hash_value=md5,
                size=int(file_system.getsize(file_path)),
                modified_time=modified_time,
                destination_path=None,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort caching
            logger.debug("Failed to cache md5 for %s: %s", file_path, exc)
    return md5

