"""Auto-skip tests that need Windows or FFmpeg when unavailable."""

import shutil
import sys

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    has_ffmpeg = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    skip_windows = pytest.mark.skip(reason="requires Windows (junctions)")
    skip_ffmpeg = pytest.mark.skip(reason="requires ffmpeg and ffprobe on PATH")
    for item in items:
        if "windows" in item.keywords and sys.platform != "win32":
            item.add_marker(skip_windows)
        if "ffmpeg" in item.keywords and not has_ffmpeg:
            item.add_marker(skip_ffmpeg)
