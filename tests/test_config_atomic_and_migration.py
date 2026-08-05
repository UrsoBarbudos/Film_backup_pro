import json
import os
from pathlib import Path

import pytest

import paths as paths_module
from config import Config


def test_migration_loads_old_when_new_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    app_data = tmp_path / "appdata"
    home.mkdir()
    app_data.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(paths_module, "get_app_data_dir", lambda: str(app_data))

    legacy_file = home / ".film_backup_pro_settings.json"
    legacy_payload = {"theme": "dark", "last_source_dir": None}
    legacy_file.write_text(json.dumps(legacy_payload), encoding="utf-8")

    cfg = Config()
    loaded = cfg.load()
    assert loaded["theme"] == "dark"
    # Новый путь не обязан появляться на load, миграция происходит на save
    assert Path(cfg.settings_file).parent == app_data
    assert not Path(cfg.settings_file).exists()


def test_save_creates_new_location_and_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    app_data = tmp_path / "appdata"
    home.mkdir()
    app_data.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(paths_module, "get_app_data_dir", lambda: str(app_data))

    cfg = Config()
    cfg.save(theme="dark")

    settings_path = Path(cfg.settings_file)
    assert settings_path.exists()
    assert not Path(str(settings_path) + ".tmp").exists()

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"


def test_save_is_atomic_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    app_data = tmp_path / "appdata"
    home.mkdir()
    app_data.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(paths_module, "get_app_data_dir", lambda: str(app_data))

    cfg = Config()

    # Создаём исходный валидный файл настроек
    cfg.save(theme="light")
    settings_path = Path(cfg.settings_file)
    original = settings_path.read_text(encoding="utf-8")

    # Фейлим os.replace, чтобы симулировать сбой на атомарной замене
    def boom(_src: str, _dst: str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)

    # save не должен «убить» основной файл, tmp должен быть убран
    cfg.save(theme="dark")
    assert settings_path.read_text(encoding="utf-8") == original
    assert not Path(str(settings_path) + ".tmp").exists()


def test_legacy_copy_mode_is_ignored_without_becoming_a_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    app_data = tmp_path / "appdata"
    home.mkdir()
    app_data.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(paths_module, "get_app_data_dir", lambda: str(app_data))

    cfg = Config()
    assert "copy_mode" not in cfg.load()

    cfg.settings_file = str(app_data / "settings.json")
    Path(cfg.settings_file).write_text(
        json.dumps({"theme": "dark", "copy_mode": "logging"}),
        encoding="utf-8",
    )
    loaded_legacy = cfg.load()
    assert loaded_legacy["theme"] == "dark"
    assert loaded_legacy["copy_mode"] == "logging"


def test_source_marker_settings_defaults_persistence_and_old_config(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    cfg = Config(settings_file=str(settings_file))
    migrated = cfg.load()
    assert migrated["mark_source_after_verified_backup"] is True
    assert migrated["warn_on_previously_backed_up_source"] is True

    cfg.save(
        mark_source_after_verified_backup=False,
        warn_on_previously_backed_up_source=False,
    )
    loaded = cfg.load()
    assert loaded["mark_source_after_verified_backup"] is False
    assert loaded["warn_on_previously_backed_up_source"] is False
