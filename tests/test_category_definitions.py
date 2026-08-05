from engine_modules.categories import (
    AUDIO_EXTENSIONS,
    PHOTO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    get_file_category,
)
from engine_modules.category_definitions import (
    CATEGORY_DEFINITIONS,
    DEFAULT_CATEGORY,
    get_category_definition,
    get_category_keys,
)


def test_canonical_category_metadata():
    assert get_category_keys() == ("Video", "Audio", "Photo")
    assert tuple(item.key for item in CATEGORY_DEFINITIONS) == ("Video", "Audio", "Photo")


def test_legacy_extension_exports_come_from_definitions():
    assert VIDEO_EXTENSIONS == get_category_definition("Video").extensions
    assert AUDIO_EXTENSIONS == get_category_definition("Audio").extensions
    assert PHOTO_EXTENSIONS == get_category_definition("Photo").extensions


def test_unknown_files_keep_existing_video_fallback():
    assert DEFAULT_CATEGORY == "Video"
    assert get_file_category("document.pdf") == DEFAULT_CATEGORY
    assert get_category_definition("Unknown") is None
