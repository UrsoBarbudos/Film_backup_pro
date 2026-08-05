from __future__ import annotations

import pytest


def test_resolve_file_system_none_raises() -> None:
    from utils import resolve_file_system

    with pytest.raises(ValueError) as excinfo:
        resolve_file_system(None)

    assert "file_system must be provided" in str(excinfo.value)


def test_main_window_view_model_passes_file_system_to_get_disk_free_space(monkeypatch) -> None:
    from ui.main_window_view_model import MainWindowViewModel

    class _State:
        destination_path = "/tmp"

        @staticmethod
        def has_destination() -> bool:
            return True

    class _Sources:
        @staticmethod
        def get_total_sources_size() -> int:
            return 0

    seen = {"called": False, "file_system": None}

    def fake_get_disk_free_space(path: str, *, file_system):
        seen["called"] = True
        seen["file_system"] = file_system
        return (100, 0, 100)

    import utils as utils_module

    monkeypatch.setattr(utils_module, "get_disk_free_space", fake_get_disk_free_space)

    vm = MainWindowViewModel(state_manager=_State(), source_manager=_Sources())
    sentinel_fs = object()
    ok, _free, _total, _required = vm.get_disk_space_info(sentinel_fs)
    assert ok is True
    assert seen["called"] is True
    assert seen["file_system"] is sentinel_fs
