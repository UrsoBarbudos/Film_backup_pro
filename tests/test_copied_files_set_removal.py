"""
Тесты для проверки удаления copied_files_set и обработки файлов из всех источников.
"""

import os
from pathlib import Path
import pytest


def _run_orchestrator(*, tmp_path: Path, src_roots: list[Path], dst_root: Path, verification_mode: str):
    """Вспомогательная функция для запуска оркестратора"""
    from repositories import FileSystemRepository
    from backup_components import BackupOrchestrator
    from backup_components.backup_run_context import BackupCallbacks, BackupDeps, BackupRunConfig, BackupTokens

    # Важно: направляем app data dir в tmp, чтобы HashStorage не писал в home.
    os.environ["FILM_BACKUP_PRO_APP_DATA_DIR"] = str(tmp_path / "app_data")

    fs = FileSystemRepository()
    logs: list[str] = []

    def log_callback(msg: str) -> None:
        logs.append(msg)

    run = BackupRunConfig(
        destination_root=str(dst_root),
        source_drives=[str(src) for src in src_roots],
        verification_mode=verification_mode,
        create_md_log=False,
        prevent_sleep=False,
    )
    tokens = BackupTokens.from_legacy(pause_event=None, pause_token=None, cancel_token=None)
    callbacks = BackupCallbacks(
        log_callback=log_callback,
        progress_callback=None,
        signals=None,
        verification_action_callback=None,
        copy_conflict_action_callback=None,
        success_callback=None,
        progress_batcher=None,
    )
    deps = BackupDeps(
        file_system=fs,
        file_copier=None,
        file_verifier=None,
        hash_storage=None,
        config=None,
    )

    orchestrator = BackupOrchestrator.create(run=run, tokens=tokens, callbacks=callbacks, deps=deps)
    orchestrator.run()

    return orchestrator, logs


class TestCopiedFilesSetRemoval:
    """Тесты для проверки удаления copied_files_set"""
    
    def test_no_copied_files_set_attribute(self, tmp_path: Path):
        """Проверяет, что атрибут copied_files_set не существует в BackupOrchestrator"""
        from backup_components import BackupOrchestrator
        
        # Проверяем, что атрибут не определен в классе
        assert not hasattr(BackupOrchestrator, 'copied_files_set')
        
        # Создаем экземпляр и проверяем, что атрибут не создается
        src_root = tmp_path / "SRC"
        dst_root = tmp_path / "DEST"
        src_root.mkdir(parents=True, exist_ok=True)
        dst_root.mkdir(parents=True, exist_ok=True)
        
        orchestrator, _logs = _run_orchestrator(
            tmp_path=tmp_path,
            src_roots=[src_root],
            dst_root=dst_root,
            verification_mode="fast",
        )
        
        # Проверяем, что атрибут не существует
        assert not hasattr(orchestrator, 'copied_files_set')
    
    def test_files_processed_from_all_sources(self, tmp_path: Path):
        """Проверяет, что файлы обрабатываются из всех источников, даже если один файл встречается в нескольких источниках"""
        src_root1 = tmp_path / "SRC1"
        src_root2 = tmp_path / "SRC2"
        dst_root = tmp_path / "DEST"
        
        src_root1.mkdir(parents=True, exist_ok=True)
        src_root2.mkdir(parents=True, exist_ok=True)
        dst_root.mkdir(parents=True, exist_ok=True)
        
        # Создаем один и тот же файл в обоих источниках
        file_content = b"same-content"
        (src_root1 / "file.bin").write_bytes(file_content)
        (src_root2 / "file.bin").write_bytes(file_content)
        
        orchestrator, logs = _run_orchestrator(
            tmp_path=tmp_path,
            src_roots=[src_root1, src_root2],
            dst_root=dst_root,
            verification_mode="fast",
        )
        
        # Оба файла должны быть обработаны
        # Файлы копируются в подпапки по имени источника.
        expected_path1 = dst_root / "SRC1" / "file.bin"
        expected_path2 = dst_root / "SRC2" / "file.bin"
        
        assert expected_path1.exists(), f"Файл из первого источника должен быть скопирован: {expected_path1}"
        assert expected_path2.exists(), f"Файл из второго источника должен быть скопирован: {expected_path2}"
        
        # Оба файла должны быть в статистике
        assert orchestrator.successful_files >= 2, "Оба файла должны быть обработаны"
    
    def test_same_file_in_multiple_sources_copied(self, tmp_path: Path):
        """Проверяет, что один и тот же файл из разных источников копируется (FileCopier обработает конфликт имен)"""
        src_root1 = tmp_path / "SRC1"
        src_root2 = tmp_path / "SRC2"
        dst_root = tmp_path / "DEST"
        
        src_root1.mkdir(parents=True, exist_ok=True)
        src_root2.mkdir(parents=True, exist_ok=True)
        dst_root.mkdir(parents=True, exist_ok=True)
        
        # Создаем файлы с одинаковым именем в обоих источниках
        (src_root1 / "video.MP4").write_bytes(b"content1")
        (src_root2 / "video.MP4").write_bytes(b"content2")
        
        orchestrator, logs = _run_orchestrator(
            tmp_path=tmp_path,
            src_roots=[src_root1, src_root2],
            dst_root=dst_root,
            verification_mode="fast",
        )
        
        # Файлы копируются в подпапки по имени источника.
        expected_path1 = dst_root / "SRC1" / "video.MP4"
        expected_path2 = dst_root / "SRC2" / "video.MP4"
        
        assert expected_path1.exists(), f"Файл из первого источника должен быть скопирован: {expected_path1}"
        assert expected_path2.exists(), f"Файл из второго источника должен быть скопирован: {expected_path2}"
        
        # Проверяем содержимое
        assert expected_path1.read_bytes() == b"content1"
        assert expected_path2.read_bytes() == b"content2"
        
        # Оба файла должны быть обработаны
        assert orchestrator.successful_files >= 2


class TestFilesProcessedFromAllSources:
    """Тесты для проверки обработки файлов из всех источников"""

    def test_single_flow_preserves_source_tree_without_generated_structure(self, tmp_path: Path):
        src_root = tmp_path / "CARD_A"
        dst_root = tmp_path / "DEST"
        (src_root / "DCIM" / "100MEDIA").mkdir(parents=True)
        dst_root.mkdir()
        (src_root / "DCIM" / "100MEDIA" / "clip.mov").write_bytes(b"media")

        orchestrator, _logs = _run_orchestrator(
            tmp_path=tmp_path,
            src_roots=[src_root],
            dst_root=dst_root,
            verification_mode="fast",
        )

        assert orchestrator.destination_root == str(dst_root)
        assert (dst_root / "CARD_A" / "DCIM" / "100MEDIA" / "clip.mov").read_bytes() == b"media"
        assert not (dst_root / "Footage").exists()
        assert not (dst_root / "Sound").exists()
        assert not (dst_root / "Photo").exists()
        assert not list(dst_root.glob("*_[0-9][0-9].[0-9][0-9].[0-9][0-9]"))
    
    def test_multiple_sources_all_files_copied(self, tmp_path: Path):
        """Проверяет, что все файлы из всех источников копируются"""
        src_root1 = tmp_path / "SRC1"
        src_root2 = tmp_path / "SRC2"
        dst_root = tmp_path / "DEST"
        
        src_root1.mkdir(parents=True, exist_ok=True)
        src_root2.mkdir(parents=True, exist_ok=True)
        dst_root.mkdir(parents=True, exist_ok=True)
        
        # Создаем разные файлы в источниках
        (src_root1 / "file1.bin").write_bytes(b"content1")
        (src_root1 / "file2.bin").write_bytes(b"content2")
        (src_root2 / "file3.bin").write_bytes(b"content3")
        (src_root2 / "file4.bin").write_bytes(b"content4")
        
        orchestrator, logs = _run_orchestrator(
            tmp_path=tmp_path,
            src_roots=[src_root1, src_root2],
            dst_root=dst_root,
            verification_mode="fast",
        )
        
        # Все файлы должны быть скопированы
        assert (dst_root / "SRC1" / "file1.bin").exists()
        assert (dst_root / "SRC1" / "file2.bin").exists()
        assert (dst_root / "SRC2" / "file3.bin").exists()
        assert (dst_root / "SRC2" / "file4.bin").exists()
        
        # Все 4 файла должны быть обработаны
        assert orchestrator.successful_files == 4
