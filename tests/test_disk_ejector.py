from unittest.mock import Mock, patch

from disk_ejector import eject_volume, external_volumes_for_sources


def test_external_volumes_for_sources_extracts_unique_volume_roots():
    sources = [
        "/Volumes/CARD_A/DCIM",
        "/Volumes/CARD_A/PRIVATE/clip.mov",
        "/Volumes/CARD_B",
        "/Users/test/Movies",
    ]

    assert external_volumes_for_sources(sources) == [
        "/Volumes/CARD_A",
        "/Volumes/CARD_B",
    ]


def test_external_volumes_for_sources_ignores_similar_non_volume_path():
    assert external_volumes_for_sources(
        ["/tmp/Volumes/CARD_A", "/Volumes", "", "/"]
    ) == []


@patch("disk_ejector.sys.platform", "darwin")
@patch("disk_ejector.subprocess.run")
def test_eject_volume_uses_diskutil_with_argument_list(run_mock):
    run_mock.return_value = Mock(returncode=0, stdout="Disk ejected", stderr="")

    result = eject_volume("/Volumes/CARD A")

    assert result.success is True
    run_mock.assert_called_once_with(
        ["diskutil", "eject", "/Volumes/CARD A"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@patch("disk_ejector.sys.platform", "darwin")
@patch("disk_ejector.subprocess.run")
def test_eject_volume_rejects_path_below_volume_root(run_mock):
    result = eject_volume("/Volumes/CARD_A/DCIM")

    assert result.success is False
    run_mock.assert_not_called()
