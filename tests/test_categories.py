"""Тесты для категоризации файлов (engine_modules/categories)."""

import pytest
from unittest.mock import Mock
from engine_modules.categories import (
    get_file_category,
    is_system_file,
    get_folder_predominant_category,
)


class TestGetFileCategory:
    def test_video_extensions(self):
        assert get_file_category("film.MP4") == "Video"
        assert get_file_category("a.mkv") == "Video"
        assert get_file_category("b.mov") == "Video"
        assert get_file_category("c.r3d") == "Video"
        assert get_file_category("d.mxf") == "Video"

    def test_audio_extensions(self):
        assert get_file_category("track.mp3") == "Audio"
        assert get_file_category("sound.wav") == "Audio"
        assert get_file_category("file.flac") == "Audio"
        assert get_file_category("file.m4a") == "Audio"

    def test_photo_extensions(self):
        assert get_file_category("img.jpg") == "Photo"
        assert get_file_category("img.jpeg") == "Photo"
        assert get_file_category("img.png") == "Photo"
        assert get_file_category("img.heic") == "Photo"

    def test_unknown_defaults_to_video(self):
        assert get_file_category("file.xyz") == "Video"
        assert get_file_category("no_ext") == "Video"

    def test_case_insensitive(self):
        assert get_file_category("FILE.MP4") == "Video"
        assert get_file_category("  file.mp3  ") == "Audio"


class TestIsSystemFile:
    def test_ds_store(self):
        assert is_system_file(".DS_Store") is True
        assert is_system_file(".ds_store") is True

    def test_resource_forks(self):
        assert is_system_file("._anything") is True
        assert is_system_file("._") is True

    def test_spotlight_and_other(self):
        assert is_system_file(".spotlight-v100") is True
        assert is_system_file(".trashes") is True
        assert is_system_file(".fseventsd") is True

    def test_regular_files(self):
        assert is_system_file("normal.mp4") is False
        assert is_system_file(".gitignore") is False

    def test_source_backup_markers_and_temporary_files(self):
        assert is_system_file("DUBLER_BACKUP_27.07.26_1030.md") is True
        assert is_system_file("DUBLER_BACKUP_27.07.26_1030_42.md") is True
        assert is_system_file("DUBLER_BACKUP_27.07.26_1030_42_abcd1234.md") is True
        assert is_system_file(
            "DUBLER_BACKUP_27.07.26_1030.md.tmp-abcd1234"
        ) is True
        assert is_system_file(".DUBLER_BACKUP_27.07.26_1030.md") is True
        assert is_system_file(".DUBLER_BACKUP_invalid.md") is False


class TestGetFolderPredominantCategory:
    def test_nonexistent_returns_video(self):
        fs = Mock()
        fs.exists = Mock(return_value=False)
        fs.isdir = Mock(return_value=False)
        assert get_folder_predominant_category("/nonexistent", fs) == "Video"

    def test_empty_folder_returns_video(self):
        fs = Mock()
        fs.exists = Mock(return_value=True)
        fs.isdir = Mock(return_value=True)
        fs.walk = Mock(return_value=iter([("/path", [], [])]))
        assert get_folder_predominant_category("/path", fs) == "Video"

    def test_predominant_video(self):
        fs = Mock()
        fs.exists = Mock(return_value=True)
        fs.isdir = Mock(return_value=True)
        fs.walk = Mock(return_value=iter([
            ("/path", [], ["a.mp4", "b.mkv", "c.mp3"]),
        ]))
        assert get_folder_predominant_category("/path", fs) == "Video"

    def test_predominant_photo(self):
        fs = Mock()
        fs.exists = Mock(return_value=True)
        fs.isdir = Mock(return_value=True)
        fs.walk = Mock(return_value=iter([
            ("/path", [], ["a.jpg", "b.png", "c.mp3"]),
        ]))
        assert get_folder_predominant_category("/path", fs) == "Photo"

    def test_skips_system_files(self):
        fs = Mock()
        fs.exists = Mock(return_value=True)
        fs.isdir = Mock(return_value=True)
        fs.walk = Mock(return_value=iter([
            ("/path", [], [".DS_Store", "._x", "film.mp4"]),
        ]))
        assert get_folder_predominant_category("/path", fs) == "Video"
