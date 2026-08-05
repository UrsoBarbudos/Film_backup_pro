"""Чтение и атомарная запись отметок об успешном backup исходного тома."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

MARKER_PREFIX = "DUBLER_BACKUP_"
MARKER_PATTERN = re.compile(
    r"^DUBLER_BACKUP_(\d{2}\.\d{2}\.\d{2})_(\d{4})"
    r"(?:_(\d{2})(?:_([A-Za-z0-9-]{4,16}))?)?\.md$"
)
LEGACY_MARKER_PATTERN = re.compile(
    r"^\.DUBLER_BACKUP_(\d{2}\.\d{2}\.\d{2})_(\d{4})"
    r"(?:_(\d{2})(?:_([A-Za-z0-9-]{4,16}))?)?\.md$"
)
TEMP_MARKER_PATTERN = re.compile(r"^\.?DUBLER_BACKUP_.*\.md\.tmp-[A-Za-z0-9-]+$")


@dataclass(frozen=True, slots=True)
class SourceBackupMarker:
    path: str
    verified_at: datetime
    destination_path: Optional[str] = None
    source_file_count: Optional[int] = None
    source_total_bytes: Optional[int] = None
    verification_mode: Optional[str] = None
    session_id: Optional[str] = None


def source_volume_root(source_path: str) -> Optional[str]:
    """Возвращает только безопасный корень ``/Volumes/<name>``."""
    try:
        resolved = Path(source_path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    parts = resolved.parts
    if len(parts) < 3 or parts[0] != os.sep or parts[1] != "Volumes":
        return None
    return str(Path(os.sep, "Volumes", parts[2]))


def is_source_backup_marker(filename: str) -> bool:
    normalized = (filename or "").strip()
    return (
        MARKER_PATTERN.fullmatch(normalized) is not None
        or LEGACY_MARKER_PATTERN.fullmatch(normalized) is not None
    )


def is_source_backup_marker_temp(filename: str) -> bool:
    return TEMP_MARKER_PATTERN.fullmatch((filename or "").strip()) is not None


class SourceBackupMarkerService:
    """Marker-сервис без зависимостей от Qt."""

    def read_latest(self, source_path: str) -> Optional[SourceBackupMarker]:
        volume_root = source_volume_root(source_path)
        if volume_root is None:
            return None
        return self.read_latest_from_volume(volume_root)

    def read_latest_from_volume(self, volume_root: str) -> Optional[SourceBackupMarker]:
        try:
            names = os.listdir(volume_root)
        except (OSError, PermissionError) as exc:
            logger.warning("Не удалось прочитать отметки на томе %s: %s", volume_root, exc)
            return None

        valid: list[SourceBackupMarker] = []
        for name in names:
            if not is_source_backup_marker(name):
                continue
            path = os.path.join(volume_root, name)
            try:
                valid.append(self._read_marker(path))
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("Повреждённая или неподдерживаемая отметка %s: %s", path, exc)
        return max(valid, key=lambda marker: marker.verified_at) if valid else None

    def write_markers(
        self,
        source_paths: Iterable[str],
        *,
        verified_at: datetime,
        metadata: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> list[str]:
        roots: list[str] = []
        for source_path in source_paths:
            root = source_volume_root(source_path)
            if root and root not in roots:
                roots.append(root)
        written: list[str] = []
        for root in roots:
            written.append(
                self.write_marker(
                    root,
                    verified_at=verified_at,
                    metadata=metadata,
                    session_id=session_id,
                )
            )
        return written

    def write_marker(
        self,
        volume_root: str,
        *,
        verified_at: datetime,
        metadata: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> str:
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValueError("verified_at должен содержать часовой пояс")
        session = (session_id or uuid.uuid4().hex)[:8]
        candidates = [
            f"{MARKER_PREFIX}{verified_at:%d.%m.%y_%H%M}.md",
            f"{MARKER_PREFIX}{verified_at:%d.%m.%y_%H%M_%S}.md",
            f"{MARKER_PREFIX}{verified_at:%d.%m.%y_%H%M_%S}_{session}.md",
        ]
        payload = self._render_document(verified_at, metadata, session)

        for name in candidates:
            target = os.path.join(volume_root, name)
            if os.path.exists(target):
                continue
            temp = f"{target}.tmp-{uuid.uuid4().hex[:8]}"
            try:
                with open(temp, "x", encoding="utf-8") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    reservation_fd = os.open(
                        target,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        0o600,
                    )
                except FileExistsError:
                    continue
                else:
                    os.close(reservation_fd)
                try:
                    os.replace(temp, target)
                except OSError:
                    try:
                        os.remove(target)
                    except OSError:
                        pass
                    raise
                return target
            finally:
                try:
                    os.remove(temp)
                except FileNotFoundError:
                    pass
        raise FileExistsError("Не удалось подобрать уникальное имя marker-файла")

    def _read_marker(self, path: str) -> SourceBackupMarker:
        with open(path, "r", encoding="utf-8") as stream:
            text = stream.read()
        fields = self._parse_front_matter(text)
        if fields.get("schema_version") != 1:
            raise ValueError("неподдерживаемая schema_version")
        verified_raw = fields.get("verified_at")
        if not isinstance(verified_raw, str):
            raise ValueError("отсутствует verified_at")
        verified_at = datetime.fromisoformat(verified_raw)
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValueError("verified_at не содержит часовой пояс")
        return SourceBackupMarker(
            path=path,
            verified_at=verified_at,
            destination_path=self._optional_str(fields.get("destination_path")),
            source_file_count=self._optional_nonnegative_int(fields.get("source_file_count")),
            source_total_bytes=self._optional_nonnegative_int(fields.get("source_total_bytes")),
            verification_mode=self._optional_str(fields.get("verification_mode")),
            session_id=self._optional_str(fields.get("session_id")),
        )

    @staticmethod
    def _parse_front_matter(text: str) -> dict[str, Any]:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("нет YAML front matter")
        fields: dict[str, Any] = {}
        for line in lines[1:]:
            if line.strip() == "---":
                return fields
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if ":" not in line:
                raise ValueError("некорректная строка YAML")
            key, raw_value = line.split(":", 1)
            key = key.strip()
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
                raise ValueError("некорректный ключ YAML")
            try:
                fields[key] = json.loads(raw_value.strip())
            except json.JSONDecodeError as exc:
                raise ValueError(f"некорректное значение {key}") from exc
        raise ValueError("front matter не закрыт")

    @staticmethod
    def _render_document(
        verified_at: datetime, metadata: dict[str, Any], session_id: str
    ) -> str:
        values = {
            "schema_version": 1,
            "verified_at": verified_at.isoformat(timespec="seconds"),
            "session_id": session_id,
            **metadata,
        }
        front_matter = "\n".join(
            f"{key}: {json.dumps(value, ensure_ascii=False)}"
            for key, value in values.items()
            if value is not None
        )
        return (
            f"---\n{front_matter}\n---\n\n"
            "# Подтверждённая резервная копия Дублёра\n\n"
            "Этот служебный файл подтверждает успешное копирование и проверку носителя.\n"
        )

    @staticmethod
    def _optional_str(value: Any) -> Optional[str]:
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _optional_nonnegative_int(value: Any) -> Optional[int]:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
