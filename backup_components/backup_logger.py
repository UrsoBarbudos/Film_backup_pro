"""
Модуль для создания MD лог-файлов процесса резервного копирования.
Отвечает только за создание и форматирование лог-файлов.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from utils import format_size
from interfaces import IFileSystemInterface
from engine_modules.category_definitions import CATEGORY_DEFINITIONS
from .operation_issue import OperationIssue, OperationIssueCode, create_operation_issue


logger = logging.getLogger(__name__)


class BackupLogger:
    """Класс для создания MD лог-файлов"""

    _STAGE_LABELS = {
        "scanning": "Сканирование",
        "planning": "Планирование",
        "copy": "Копирование",
        "copying": "Копирование",
        "verification": "Проверка",
        "finalization": "Финализация",
    }

    def __init__(self) -> None:
        self.last_issue: Optional[OperationIssue] = None
    
    def create_md_log_file(
        self,
        destination_root: str,
        source_drives: List[str],
        start_time: datetime,
        end_time: datetime,
        total_files: int,
        successful_files: int,
        failed_files: int,
        copied_files: Dict[str, List[Dict[str, str]]],
        file_system: IFileSystemInterface,
        issues: Optional[List[Dict[str, Any]]] = None,
        report_directory: Optional[str] = None,
    ) -> str:
        """
        Создает MD лог-файл с информацией о сессии резервного копирования.

        :param destination_root: Корневая директория назначения
        :param source_drives: Список дисков-источников
        :param start_time: Время начала копирования
        :param end_time: Время окончания копирования
        :param total_files: Общее количество файлов
        :param successful_files: Количество успешно скопированных файлов
        :param failed_files: Количество файлов с ошибками
        :param copied_files: Словарь с информацией о скопированных файлах по категориям
                           Формат: {'Video': [{'path': '...', 'size': 12345}, ...], ...}
        :param file_system: Интерфейс файловой системы (обязателен, explicit DI)
        :param report_directory: Каталог файла отчёта; по умолчанию destination_root
        :return: Путь к созданному лог-файлу
        """
        fs = file_system
        self.last_issue = None
        tmp_path: Optional[str] = None
        report_stage = "report.write"
        try:
            # Формируем имя файла с временной меткой
            timestamp = end_time.strftime("%Y-%m-%d_%H-%M-%S")
            log_filename = f"backup_log_{timestamp}.md"
            report_root = report_directory or destination_root
            fs.makedirs(report_root, exist_ok=True)
            log_path = fs.join(report_root, log_filename)
            
            # Вычисляем длительность
            duration = end_time - start_time
            duration_seconds = int(duration.total_seconds())
            duration_minutes = duration_seconds // 60
            duration_secs = duration_seconds % 60
            
            # Формируем содержимое MD файла
            md_content = []
            md_content.append("# Лог резервного копирования\n")
            
            # Информация о сессии
            md_content.append("## Информация о сессии\n")
            md_content.append(f"- **Дата начала:** {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            md_content.append(f"- **Дата окончания:** {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            md_content.append(f"- **Длительность:** {duration_minutes} минут {duration_secs} секунд\n")
            md_content.append("\n")
            
            # Назначение
            md_content.append("## Назначение\n")
            md_content.append(f"- **Путь:** {destination_root}\n")
            md_content.append("\n")
            
            # Источники
            md_content.append("## Источники\n")
            for i, drive in enumerate(source_drives, 1):
                md_content.append(f"{i}. {drive}\n")
            md_content.append("\n")
            
            # Статистика
            md_content.append("## Статистика\n")
            md_content.append(f"- **Всего файлов:** {total_files}\n")
            md_content.append(f"- **Успешно скопировано:** {successful_files}\n")
            md_content.append(f"- **Ошибок:** {failed_files}\n")
            md_content.append("\n")

            # Скопированные файлы по категориям
            md_content.append("## Скопированные файлы\n")
            
            for category in (definition.key for definition in CATEGORY_DEFINITIONS):
                if category in copied_files and copied_files[category]:
                    md_content.append(f"\n### {category}\n")
                    for file_info in copied_files[category]:
                        file_path = file_info.get('path', '')
                        file_size = file_info.get('size', 0)
                        size_str = format_size(file_size) if isinstance(file_size, int) else str(file_size)
                        rel_path = (
                            fs.relpath(file_path, destination_root)
                            if file_path.startswith(destination_root)
                            else file_path
                        )
                        md_content.append(f"- `{rel_path}` ({size_str})\n")

            if issues:
                md_content.append("\n## Ошибки\n")
                for index, issue in enumerate(issues, 1):
                    title = self._escape_markdown(issue.get("message") or "Ошибка операции")
                    md_content.append(f"\n### {index}. {title}\n")
                    self._append_issue_field(
                        md_content, "Файл", issue.get("file_name"), code=True
                    )
                    self._append_issue_field(
                        md_content, "Источник", issue.get("source_path"), code=True
                    )
                    self._append_issue_field(
                        md_content, "Назначение", issue.get("destination_path"), code=True
                    )
                    self._append_issue_field(
                        md_content,
                        "Этап",
                        self._format_stage(issue.get("stage")),
                    )
                    self._append_issue_field(
                        md_content, "Причина", issue.get("message")
                    )
                    self._append_issue_field(
                        md_content, "Код", issue.get("code"), code=True
                    )
                    self._append_issue_field(
                        md_content,
                        "Время",
                        self._format_issue_timestamp(issue.get("timestamp")),
                        code=True,
                    )
                    self._append_issue_field(
                        md_content,
                        "Техническая информация",
                        issue.get("technical_message"),
                    )
                    if issue.get("fatal"):
                        md_content.append("- **Критическая ошибка:** Да\n")
            
            # Записываем файл атомарно: temp -> replace (без «обрубленного» файла при сбое)
            tmp_path = log_path + ".tmp"
            report_stage = "report.write"
            with fs.open(tmp_path, 'w', encoding='utf-8') as f:
                f.writelines(md_content)
                report_stage = "report.fsync"
                f.flush()
                import os
                os.fsync(f.fileno())

            report_stage = "report.replace"
            fs.replace(tmp_path, log_path)
            tmp_path = None
            
            logger.info("MD лог-файл создан: %s", log_path)
            return log_path
        except Exception as e:
            logger.exception("Не удалось создать MD лог-файл: %s", e)
            code = (
                None
                if isinstance(e, OSError)
                else OperationIssueCode.REPORT_WRITE_FAILED
            )
            self.last_issue = create_operation_issue(
                e,
                stage=report_stage,
                destination_path=destination_root,
                file_name=fs.basename(log_path) if "log_path" in locals() else None,
                code=code,
            )
            if tmp_path:
                try:
                    if fs.exists(tmp_path):
                        fs.remove(tmp_path)
                except OSError as cleanup_error:
                    logger.warning(
                        "Не удалось удалить временный Markdown-отчёт %s: %s",
                        tmp_path,
                        cleanup_error,
                    )
            return ""

    @classmethod
    def _format_stage(cls, stage: Any) -> str:
        value = str(stage or "")
        root = value.split(".", 1)[0]
        return cls._STAGE_LABELS.get(root, value)

    @staticmethod
    def _format_issue_timestamp(value: Any) -> Optional[str]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _escape_markdown(value: Any) -> str:
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        text = " / ".join(part.strip() for part in text.split("\n") if part.strip())
        for character in ("\\", "*", "_", "[", "]", "<", ">", "#", "|"):
            text = text.replace(character, f"\\{character}")
        return text

    @staticmethod
    def _code_span(value: Any) -> str:
        text = str(value).replace("\r", " ").replace("\n", " ")
        delimiter = "``" if "`" in text else "`"
        padding = " " if "`" in text else ""
        return f"{delimiter}{padding}{text}{padding}{delimiter}"

    @classmethod
    def _append_issue_field(
        cls,
        output: List[str],
        label: str,
        value: Any,
        *,
        code: bool = False,
    ) -> None:
        if value is None:
            return
        formatted = cls._code_span(value) if code else cls._escape_markdown(value)
        output.append(f"- **{label}:** {formatted}\n")
