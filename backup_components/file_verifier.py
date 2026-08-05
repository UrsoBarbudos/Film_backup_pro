"""
Модуль для проверки целостности файлов в процессе резервного копирования.
Отвечает только за проверку целостности скопированных файлов.
"""

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING
from interfaces import IFileSystemInterface
from .copy_verification_result import CopyVerificationResult
from .operation_issue import OperationIssueCode, create_message_issue, create_operation_issue
from .operation_results import VerificationResult
from .exceptions import BackupCancelledError
from .retry_handler import RetryHandler
from .control_tokens import CancelToken
from .deduplication_manager import (
    get_or_compute_sample_signature,
    get_or_compute_md5
)
from utils import get_file_sizes_for_compare

if TYPE_CHECKING:
    from .hash_storage import HashStorage


logger = logging.getLogger(__name__)


class FileVerifier:
    """Класс для проверки целостности файлов"""
    
    # Размер chunk для sample_signature при верификации
    _VERIFICATION_SAMPLE_CHUNK_SIZE_BYTES = 1024 * 1024  # 1MB
    
    def __init__(
        self, 
        log_callback: Optional[Callable[[str], None]] = None,
        file_system: Optional[IFileSystemInterface] = None,
        cancel_token: Optional[CancelToken] = None,
        verification_mode: str = 'full',
        hash_storage: Optional['HashStorage'] = None,
        verification_run_id: Optional[str] = None,
    ):
        """
        Инициализация верификатора файлов
        
        :param log_callback: Функция для логирования операций
        :param file_system: Интерфейс файловой системы (опционально, для обратной совместимости)
        :param cancel_token: CancelToken для проверки отмены операции (опционально)
        :param verification_mode: Режим проверки - 'full' (MD5) или 'fast' (размер файла)
        :param hash_storage: Хранилище хешей для получения сохраненных хешей (опционально)
        """
        self.log_callback = log_callback or (lambda msg: None)
        self.fs = file_system
        self.cancel_token = cancel_token
        self.verification_mode = verification_mode
        self.hash_storage = hash_storage
        self.verification_run_id = verification_run_id
        self._consumed_operation_ids: set[str] = set()
        self.verification_read_bytes = 0
        
        # Инициализируем RetryHandler для обработки временных ошибок
        self.retry_handler = RetryHandler(
            max_attempts=3,
            delay=1.0,
            log_callback=self.log_callback
        )

        if self.fs is None:
            raise ValueError("file_system must be provided to FileVerifier (explicit DI).")
    
    def verify_file(
        self,
        source_path: str,
        destination_path: str,
        copy_verification_result: Optional[CopyVerificationResult] = None,
    ) -> VerificationResult:
        """
        Проверяет целостность скопированного файла.
        
        В зависимости от режима проверки использует:
        - 'full': сравнение MD5 контрольных сумм
        - 'fast': сравнение размеров файлов
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к скопированному файлу
        :return: Структурированный результат проверки
        """
        try:
            # Проверяем отмену в начале
            if self.cancel_token:
                self.cancel_token.raise_if_cancelled("Проверка отменена пользователем")
            
            # Проверяем существование обоих файлов (с повторными попытками)
            if not self.retry_handler.retry_on_temporary_error(
                self.fs.exists, source_path
            ):
                error_msg = f"❌ Исходный файл не найден: {source_path}"
                logger.error("%s", error_msg)
                self.log_callback(error_msg)
                return VerificationResult(
                    success=False,
                    issue=create_message_issue(
                        stage="verification",
                        code=OperationIssueCode.SOURCE_NOT_FOUND,
                        message="Исходный файл не найден во время проверки",
                        source_path=source_path,
                        destination_path=destination_path,
                        file_name=self.fs.basename(source_path),
                    ),
                )
            
            if not self.retry_handler.retry_on_temporary_error(
                self.fs.exists, destination_path
            ):
                error_msg = f"❌ Скопированный файл не найден: {destination_path}"
                logger.error("%s", error_msg)
                self.log_callback(error_msg)
                return VerificationResult(
                    success=False,
                    issue=create_message_issue(
                        stage="verification",
                        code=OperationIssueCode.DESTINATION_UNAVAILABLE,
                        message="Скопированный файл не найден во время проверки",
                        source_path=source_path,
                        destination_path=destination_path,
                        file_name=self.fs.basename(source_path),
                    ),
                )
            
            filename = self.fs.basename(source_path)
            
            # Выбираем метод проверки в зависимости от режима
            if self.verification_mode == 'fast':
                return self._verify_by_size(source_path, destination_path, filename)
            else:
                if self._accept_copy_verification_result(
                    source_path,
                    destination_path,
                    copy_verification_result,
                ):
                    return VerificationResult(success=True)
                # Режим 'full' - проверка MD5
                return self._verify_by_checksum(source_path, destination_path, filename)
        except BackupCancelledError:
            # Пробрасываем BackupCancelledError дальше для корректной обработки отмены
            raise
        except Exception as e:
            error_msg = f"❌ Ошибка при проверке файла {source_path}: {e}"
            logger.exception("%s", error_msg)
            self.log_callback(error_msg)
            return VerificationResult(
                success=False,
                issue=create_operation_issue(
                    e,
                    stage="verification",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=self.fs.basename(source_path),
                ),
            )

    def _accept_copy_verification_result(
        self,
        source_path: str,
        destination_path: str,
        result: Optional[CopyVerificationResult],
    ) -> bool:
        """Принимает только одноразовое доказательство из текущего запуска."""
        if (
            result is None
            or self.verification_mode != "full"
            or self.verification_run_id is None
            or result.run_id != self.verification_run_id
            or result.operation_id in self._consumed_operation_ids
            or result.verification_mode != "full"
            or not result.verified_temporary_file
            or not result.temporary_file_synced_and_closed
            or not result.atomically_finalized
            or result.source_md5 != result.destination_md5
            or result.source_size != result.destination_size
        ):
            return False

        normalized_source = Path(os.path.realpath(os.path.abspath(source_path)))
        normalized_destination = Path(os.path.realpath(os.path.abspath(destination_path)))
        if (
            result.source_path != normalized_source
            or result.destination_path != normalized_destination
        ):
            return False

        current_source_size = self.retry_handler.retry_on_temporary_error(
            self.fs.getsize, source_path
        )
        current_destination_size = self.retry_handler.retry_on_temporary_error(
            self.fs.getsize, destination_path
        )
        if (
            current_source_size != result.source_size
            or current_destination_size != result.destination_size
        ):
            return False

        self._consumed_operation_ids.add(result.operation_id)
        logger.debug(
            "Повторный MD5 пропущен: принята проверка текущей операции %s",
            result.operation_id,
        )
        return True
    
    def _verify_by_checksum(
        self,
        source_path: str,
        destination_path: str,
        filename: str
    ) -> VerificationResult:
        """
        Проверяет файлы трёхфазным методом (Level A: размер → Level B: sample_signature → Level C: MD5).
        HashStorage допустим для источника и sample_signature, но полный MD5
        назначения без доказательства текущей операции всегда вычисляется заново.
        
        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к скопированному файлу
        :param filename: Имя файла для логирования
        :return: Структурированный результат проверки
        """
        # Проверяем отмену перед началом проверки
        if self.cancel_token:
            self.cancel_token.raise_if_cancelled("Проверка отменена пользователем")
        
        size_result = self._verify_by_size(source_path, destination_path, filename)
        if not size_result.success:
            return size_result

        # Level B: Проверка sample_signature (быстрая проверка содержимого)
        self.log_callback(f"Проверяю sample_signature: {filename}...")
        logger.debug("Level B: Вычисление sample_signature исходного файла...")
        
        try:
            src_sample = get_or_compute_sample_signature(
                file_path=source_path,
                file_system=self.fs,
                chunk_size_bytes=self._VERIFICATION_SAMPLE_CHUNK_SIZE_BYTES,
                hash_storage=self.hash_storage,
            )
        except Exception as exc:
            logger.exception("Ошибка расчёта sample signature источника %s", source_path)
            return VerificationResult(
                success=False,
                issue=create_operation_issue(
                    exc,
                    stage="verification.sample_hash",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=filename,
                    code=(
                        None
                        if isinstance(exc, OSError)
                        else OperationIssueCode.HASH_CALCULATION_FAILED
                    ),
                    message="Не удалось рассчитать контрольную выборку исходного файла",
                ),
            )
        logger.debug("Sample signature исходного файла: %s", src_sample)
        
        logger.debug("Level B: Вычисление sample_signature скопированного файла...")
        try:
            dst_sample = get_or_compute_sample_signature(
                file_path=destination_path,
                file_system=self.fs,
                chunk_size_bytes=self._VERIFICATION_SAMPLE_CHUNK_SIZE_BYTES,
                hash_storage=self.hash_storage,
            )
        except Exception as exc:
            logger.exception("Ошибка расчёта sample signature назначения %s", destination_path)
            return VerificationResult(
                success=False,
                issue=create_operation_issue(
                    exc,
                    stage="verification.sample_hash",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=filename,
                    code=(
                        None
                        if isinstance(exc, OSError)
                        else OperationIssueCode.HASH_CALCULATION_FAILED
                    ),
                    message="Не удалось рассчитать контрольную выборку скопированного файла",
                ),
            )
        logger.debug("Sample signature скопированного файла: %s", dst_sample)
        
        if src_sample != dst_sample:
            error_msg = f"❌ Sample signature не совпадает для файла: {filename}!"
            logger.error("%s (src_sample=%s, dst_sample=%s)", error_msg, src_sample, dst_sample)
            self.log_callback(error_msg)
            return VerificationResult(
                success=False,
                issue=create_message_issue(
                    stage="verification.sample_hash",
                    code=OperationIssueCode.HASH_MISMATCH,
                    message="Контрольная выборка копии не совпадает с исходным файлом",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=filename,
                    technical_message=f"source={src_sample}; destination={dst_sample}",
                ),
            )
        
        logger.debug("Level B пройден: sample_signature совпадает")
        
        # Level C: Проверка полного MD5 (только если размеры и sample совпали)
        self.log_callback(f"Проверяю целостность (MD5): {filename}...")
        logger.debug("Level C: Получение/вычисление MD5 исходного файла...")
        
        try:
            src_md5 = get_or_compute_md5(
                file_path=source_path,
                file_system=self.fs,
                hash_storage=self.hash_storage,
                cancel_token=self.cancel_token,
            )
        except BackupCancelledError:
            raise
        except Exception as exc:
            logger.exception("Ошибка расчёта MD5 источника %s", source_path)
            return VerificationResult(
                success=False,
                issue=create_operation_issue(
                    exc,
                    stage="verification.hash",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=filename,
                    code=(
                        None
                        if isinstance(exc, OSError)
                        else OperationIssueCode.HASH_CALCULATION_FAILED
                    ),
                    message="Не удалось рассчитать контрольную сумму исходного файла",
                ),
            )
        logger.debug("MD5 исходного файла: %s", src_md5)
        
        logger.debug("Level C: Получение/вычисление MD5 скопированного файла...")
        # Долговременный HashStorage не является доказательством текущей операции.
        # Без принятого CopyVerificationResult назначение всегда читается полностью.
        try:
            dst_md5 = self._calculate_destination_md5(destination_path)
        except BackupCancelledError:
            raise
        except Exception as exc:
            logger.exception("Ошибка расчёта MD5 назначения %s", destination_path)
            return VerificationResult(
                success=False,
                issue=create_operation_issue(
                    exc,
                    stage="verification.hash",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=filename,
                    code=(
                        None
                        if isinstance(exc, OSError)
                        else OperationIssueCode.HASH_CALCULATION_FAILED
                    ),
                    message="Не удалось рассчитать контрольную сумму скопированного файла",
                ),
            )
        self._cache_fresh_destination_md5(destination_path, dst_md5)
        logger.debug("MD5 скопированного файла: %s", dst_md5)
        
        if src_md5 == dst_md5:
            success_msg = f"✅ Файл {filename} проверен успешно (MD5)."
            logger.info("%s", success_msg)
            self.log_callback(success_msg)
            return VerificationResult(success=True)
        else:
            error_msg = f"❌ Контрольная сумма не совпадает для файла: {filename}!"
            logger.error("%s (src=%s, dst=%s)", error_msg, src_md5, dst_md5)
            self.log_callback(error_msg)
            return VerificationResult(
                success=False,
                issue=create_message_issue(
                    stage="verification.hash",
                    code=OperationIssueCode.HASH_MISMATCH,
                    message="Контрольная сумма копии не совпадает с исходным файлом",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=filename,
                    technical_message=f"source={src_md5}; destination={dst_md5}",
                ),
            )

    def _calculate_destination_md5(self, destination_path: str) -> str:
        """Полностью читает назначение и учитывает фактический объём fallback-проверки."""
        hash_md5 = hashlib.md5()
        with self.retry_handler.retry_on_temporary_error(
            self.fs.open, destination_path, "rb"
        ) as file_object:
            while True:
                if self.cancel_token:
                    self.cancel_token.raise_if_cancelled(
                        "Проверка назначения отменена пользователем"
                    )
                chunk = file_object.read(8 * 1024 * 1024)
                if not chunk:
                    return hash_md5.hexdigest()
                self.verification_read_bytes += len(chunk)
                hash_md5.update(chunk)

    def _cache_fresh_destination_md5(
        self, destination_path: str, destination_md5: str
    ) -> None:
        """Вторично сохраняет свежий MD5, не используя кэш как канал доверия."""
        if self.hash_storage is None:
            return
        try:
            modified_time = datetime.fromtimestamp(
                self.fs.getmtime(destination_path)
            ).isoformat()
            self.hash_storage.set_hash(
                file_path=destination_path,
                hash_value=destination_md5,
                size=self.fs.getsize(destination_path),
                modified_time=modified_time,
            )
        except Exception as exc:
            logger.warning(
                "Не удалось сохранить свежий MD5 назначения %s: %s",
                destination_path,
                exc,
            )
    
    def _verify_by_size(
        self,
        source_path: str,
        destination_path: str,
        filename: str
    ) -> VerificationResult:
        """
        Проверяет файлы путем сравнения их размеров.

        :param source_path: Путь к исходному файлу
        :param destination_path: Путь к скопированному файлу
        :param filename: Имя файла для логирования
        :return: Кортеж (успех: bool, сообщение_об_ошибке: str)
        """
        self.log_callback(f"Проверяю размер файла: {filename}...")
        try:
            src_size, dst_size = get_file_sizes_for_compare(
                source_path, destination_path, self.fs, retry_handler=self.retry_handler
            )
        except (ValueError, OSError) as e:
            error_msg = str(e)
            logger.error("Ошибка при проверке размера файла %s: %s", filename, error_msg)
            self.log_callback(f"❌ {error_msg}")
            return VerificationResult(
                success=False,
                issue=create_operation_issue(
                    e,
                    stage="verification.size",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=filename,
                    message="Не удалось получить размеры файлов для проверки",
                ),
            )
        except Exception as e:
            error_msg = f"Неожиданная ошибка при проверке размеров: {e}"
            logger.error("Ошибка при проверке размера файла %s: %s", filename, error_msg)
            self.log_callback(f"❌ {error_msg}")
            return VerificationResult(
                success=False,
                issue=create_operation_issue(
                    e,
                    stage="verification.size",
                    source_path=source_path,
                    destination_path=destination_path,
                    file_name=filename,
                ),
            )

        if src_size == dst_size:
            success_msg = f"✅ Файл {filename} проверен успешно (размер совпадает)."
            logger.info("%s", success_msg)
            self.log_callback(success_msg)
            return VerificationResult(success=True)
        error_msg = f"❌ Размеры файлов не совпадают для файла: {filename}! (исходный: {src_size} байт, скопированный: {dst_size} байт)"
        logger.error("%s", error_msg)
        self.log_callback(error_msg)
        return VerificationResult(
            success=False,
            issue=create_message_issue(
                stage="verification.size",
                code=OperationIssueCode.FILE_SIZE_MISMATCH,
                message="Размер копии не совпадает с исходным файлом",
                source_path=source_path,
                destination_path=destination_path,
                file_name=filename,
                technical_message=f"source={src_size}; destination={dst_size}",
            ),
        )
