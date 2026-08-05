from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from interfaces import IFileSystemInterface
from operation_issue import (
    OperationIssue,
    OperationIssueCode,
    create_message_issue,
    create_operation_issue,
)

from .categories import get_file_category, is_system_file


@dataclass(frozen=True)
class PlannedCopy:
    """Неизменяемый элемент плана текущего задания."""

    source_path: Path
    relative_path: Path
    size: int
    modified_ns: int | None
    category: str | None
    source_root: Path
    is_single_file: bool = False


@dataclass
class ScanResult:
    """Результат единого сканирования источников"""
    total_size: int
    total_files: int
    files_list: List[PlannedCopy]
    source_sizes: Dict[str, int]  # размеры по источникам
    issues: List[OperationIssue]


def scan_sources_unified(
    source_drives: list,
    destination_root: str,
    log_callback,
    file_system: IFileSystemInterface,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> ScanResult:
    """
    Единое сканирование источников за один проход.
    Собирает размер, список файлов и метаданные одновременно.
    
    :param source_drives: Список путей к источникам
    :param destination_root: Выбранная папка назначения
    :param log_callback: Функция для логирования
    :param file_system: Интерфейс файловой системы
    :param should_cancel: Опциональная функция для проверки отмены
    :return: ScanResult с результатами сканирования
    """
    fs = file_system
    
    total_size = 0
    total_files = 0
    all_files: List[PlannedCopy] = []
    source_sizes: Dict[str, int] = {}
    issues: List[OperationIssue] = []
    assigned_root_names: set[str] = set()
    reserved_source_names = {
        fs.basename(str(path).rstrip("/")) or f"source_{index}"
        for index, path in enumerate(source_drives, 1)
    }
    single_file_names = {
        fs.basename(str(path))
        for path in source_drives
        if fs.isfile(str(path))
    }
    
    for source_index, source_path in enumerate(source_drives, 1):
        if should_cancel and should_cancel():
            break
            
        if log_callback:
            source_name = fs.basename(source_path.rstrip("/")) or source_path
            log_callback(f"Сканирование источника {source_index} из {len(source_drives)}: {source_name}")
        
        if not fs.exists(source_path):
            if log_callback:
                log_callback(f"⚠️  Источник не найден: {source_path}")
            issues.append(
                create_message_issue(
                    stage="scanning",
                    code=OperationIssueCode.SOURCE_NOT_FOUND,
                    message="Источник не найден во время сканирования",
                    source_path=source_path,
                    file_name=fs.basename(source_path.rstrip("/")) or None,
                )
            )
            continue
        
        source_files = 0
        source_size = 0
        
        try:
            if fs.isfile(source_path):
                if is_system_file(fs.basename(source_path)):
                    if log_callback:
                        log_callback(f"⚠️  Пропущен системный файл: {source_path}")
                    continue
                
                try:
                    file_size = fs.getsize(source_path)
                    source_size = file_size
                    source_files = 1
                    total_files += 1
                    
                    filename = fs.basename(source_path)
                    category = get_file_category(filename)
                    all_files.append(
                        PlannedCopy(
                            source_path=Path(source_path),
                            relative_path=Path(filename),
                            size=file_size,
                            modified_ns=_get_modified_ns(fs, source_path),
                            category=category,
                            source_root=Path(source_path),
                            is_single_file=True,
                        )
                    )
                except (OSError, FileNotFoundError, PermissionError) as exc:
                    if log_callback:
                        log_callback(f"⚠️  Ошибка доступа к файлу {source_path}")
                    issues.append(
                        create_operation_issue(
                            exc,
                            stage="scanning",
                            source_path=source_path,
                            file_name=fs.basename(source_path),
                            code=OperationIssueCode.SOURCE_UNREADABLE,
                            message="Не удалось прочитать исходный файл при сканировании",
                        )
                    )
                    continue
            
            elif fs.isdir(source_path):
                base_root_name = fs.basename(source_path.rstrip("/")) or f"source_{source_index}"
                disk_name = base_root_name
                suffix = 2
                if disk_name in single_file_names:
                    disk_name = f"{base_root_name}_{suffix}"
                    suffix += 1
                while disk_name in assigned_root_names or (
                    disk_name in reserved_source_names and disk_name != base_root_name
                ):
                    disk_name = f"{base_root_name}_{suffix}"
                    suffix += 1
                assigned_root_names.add(disk_name)
                
                def record_walk_error(path: str, exc: OSError) -> None:
                    issue = create_operation_issue(
                        exc,
                        stage="scanning",
                        source_path=path,
                        file_name=fs.basename(path.rstrip("/")) or None,
                        code=OperationIssueCode.SCAN_FAILED,
                        message="Не удалось прочитать элемент источника при сканировании",
                    )
                    issues.append(issue)
                    if log_callback:
                        log_callback(f"⚠️  Ошибка сканирования {path}: {exc}")

                walk_with_errors = getattr(fs, "walk_with_errors", None)
                walk_iterator = (
                    walk_with_errors(source_path, record_walk_error)
                    if callable(walk_with_errors)
                    else fs.walk(source_path)
                )
                for dirpath, _, filenames in walk_iterator:
                    if should_cancel and should_cancel():
                        break
                    
                    for filename in filenames:
                        if should_cancel and should_cancel():
                            break
                        
                        if is_system_file(filename):
                            continue
                        
                        filepath = fs.join(dirpath, filename)
                        try:
                            file_size = fs.getsize(filepath)
                            source_size += file_size
                            source_files += 1
                            total_files += 1
                            
                            category = get_file_category(filename)
                            rel_path = fs.relpath(dirpath, source_path)
                            root_folder = disk_name
                            if rel_path == ".":
                                subfolder_path = ""
                            else:
                                subfolder_path = rel_path
                            destination_relative_path = Path(root_folder)
                            if subfolder_path:
                                destination_relative_path /= Path(subfolder_path)
                            destination_relative_path /= filename

                            all_files.append(
                                PlannedCopy(
                                    source_path=Path(filepath),
                                    relative_path=destination_relative_path,
                                    size=file_size,
                                    modified_ns=_get_modified_ns(fs, filepath),
                                    category=category,
                                    source_root=Path(source_path),
                                )
                            )
                        except (OSError, FileNotFoundError, PermissionError) as exc:
                            issues.append(
                                create_operation_issue(
                                    exc,
                                    stage="scanning",
                                    source_path=filepath,
                                    file_name=filename,
                                    code=OperationIssueCode.SOURCE_UNREADABLE,
                                    message="Не удалось прочитать файл при сканировании",
                                )
                            )
                            if log_callback:
                                log_callback(f"⚠️  Ошибка доступа к файлу {filepath}: {exc}")
            else:
                if log_callback:
                    log_callback(f"⚠️  Неизвестный тип пути: {source_path}")
                continue
        
        except (OSError, PermissionError) as e:
            if log_callback:
                log_callback(f"⚠️  Ошибка доступа к источнику {source_path}: {e}")
            issues.append(
                create_operation_issue(
                    e,
                    stage="scanning",
                    source_path=source_path,
                    file_name=fs.basename(source_path.rstrip("/")) or None,
                    code=OperationIssueCode.SCAN_FAILED,
                )
            )
            continue
        
        total_size += source_size
        source_sizes[source_path] = source_size
        
        if log_callback:
            from utils import format_size
            
            size_str = format_size(source_size)
            source_type = "файл" if fs.isfile(source_path) else "папка"
            log_callback(f"✓ Источник {source_index} ({source_type}): {source_files} файлов, {size_str}")
    
    if log_callback:
        from utils import format_size
        
        total_size_str = format_size(total_size)
        log_callback(f"✓ Сканирование завершено: {total_files} файлов, общий объём {total_size_str}")
    
    return ScanResult(
        total_size=total_size,
        total_files=total_files,
        files_list=all_files,
        source_sizes=source_sizes,
        issues=issues,
    )


def _get_modified_ns(file_system: IFileSystemInterface, path: str) -> int | None:
    """Получает mtime с максимально доступной backend-точностью."""
    try:
        getmtime_ns = getattr(file_system, "getmtime_ns", None)
        if getmtime_ns is not None:
            return int(getmtime_ns(path))
        return int(file_system.getmtime(path) * 1_000_000_000)
    except (OSError, FileNotFoundError, PermissionError):
        return None


def scan_total_size(
    source_drives: list,
    log_callback,
    file_system: IFileSystemInterface,
) -> int:
    """
    Предварительно сканирует все источники для подсчёта общего объёма.
    Поддерживает как папки, так и отдельные файлы.
    
    Примечание: Эта функция теперь является оберткой над scan_sources_unified()
    для обратной совместимости.
    """
    result = scan_sources_unified(
        source_drives=source_drives,
        destination_root="/tmp",
        log_callback=log_callback,
        file_system=file_system,
    )
    return result.total_size
