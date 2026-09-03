"""Shared fixtures.

Settings are constructed explicitly in tests rather than read from the
environment. Explicit keyword arguments take priority over .env and the process
environment in pydantic-settings, which keeps these tests deterministic on a
developer machine that has a populated ml-pipeline/.env.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.config import Settings

# A fixed synthetic epoch. Every worker in a run shares one of these; the tests
# pin it so expected timestamps can be written out literally.
TEST_EPOCH_AT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

TEST_VIDEO_FPS = 10.0
TEST_VIDEO_FRAME_COUNT = 10
TEST_VIDEO_WIDTH_PX = 64
TEST_VIDEO_HEIGHT_PX = 48


@pytest.fixture
def epoch_at() -> datetime:
    """The shared synthetic start time for a test run."""
    return TEST_EPOCH_AT


@pytest.fixture
def strided_settings(tmp_path: Path) -> Settings:
    """Settings with FRAME_STRIDE=3, for the timestamp arithmetic test."""
    return Settings(
        FRAME_STRIDE=3,
        PLAYBACK_FPS=TEST_VIDEO_FPS,
        CROP_STORAGE_PATH=tmp_path / "crops",
    )


@pytest.fixture
def lifecycle_settings(tmp_path: Path) -> Settings:
    """Settings with small, readable tracklet lifecycle bounds.

    TRACK_LOST_FRAMES and TRACKLET_MIN_FRAMES are deliberately tiny so the
    tests read as arithmetic rather than as loops over thirty frames.
    BEST_SHOT_MIN_AREA_PX is zero so the lifecycle tests are not entangled with
    the crop-size filter.
    """
    return Settings(
        TRACK_LOST_FRAMES=3,
        TRACKLET_MIN_FRAMES=4,
        BEST_SHOT_MIN_AREA_PX=0,
        CROP_STORAGE_PATH=tmp_path / "crops",
    )


@pytest.fixture
def ten_frame_video(tmp_path: Path) -> Path:
    """Write a real 10-frame video and return its path.

    Written with MJPG into an .avi container: it encodes reliably under
    opencv-python-headless without a system codec, and reports its frame rate
    back accurately, which the timestamp test depends on.

    Each frame is filled with its own index as a grey level, so a decoded frame
    identifies which source frame it came from.
    """
    video_path = tmp_path / "camera.avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(
        str(video_path),
        fourcc,
        TEST_VIDEO_FPS,
        (TEST_VIDEO_WIDTH_PX, TEST_VIDEO_HEIGHT_PX),
    )
    assert writer.isOpened(), "could not open VideoWriter; MJPG/avi unavailable"

    for frame_index in range(TEST_VIDEO_FRAME_COUNT):
        grey_level = 10 + frame_index * 10
        frame = np.full(
            (TEST_VIDEO_HEIGHT_PX, TEST_VIDEO_WIDTH_PX, 3), grey_level, dtype=np.uint8
        )
        writer.write(frame)

    writer.release()
    return video_path
