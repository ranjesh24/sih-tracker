"""Frame timestamp arithmetic, including its interaction with FRAME_STRIDE.

This is the highest-consequence arithmetic in the pipeline. A timestamp error
here does not present as a timing bug — it presents as a matching bug in the
backend's spatio-temporal gate, which starts rejecting correct matches as
TEMPORAL_TOO_FAST. See the module docstring in src/video_source.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.config import Settings
from src.video_source import VideoSource, frame_timestamp, to_iso8601_utc

from tests.conftest import TEST_VIDEO_FPS


def test_frame_timestamp_is_epoch_plus_index_over_fps(epoch_at: datetime) -> None:
    stamp = frame_timestamp(epoch_at, frame_index=30, fps=10.0)

    assert stamp == "2026-01-01T00:00:03.000Z"


def test_frame_timestamp_of_first_frame_is_the_epoch(epoch_at: datetime) -> None:
    stamp = frame_timestamp(epoch_at, frame_index=0, fps=10.0)

    assert stamp == "2026-01-01T00:00:00.000Z"


def test_strided_timestamps_follow_the_true_frame_index(
    ten_frame_video: Path,
    strided_settings: Settings,
    epoch_at: datetime,
) -> None:
    """With FRAME_STRIDE=3, kept frames are 0,3,6,9 and are timed as such.

    The failure this guards against is timing the kept frames consecutively
    (0.0, 0.1, 0.2, 0.3) instead of by their true index (0.0, 0.3, 0.6, 0.9).
    That compresses the synthetic clock by the stride factor, so a vehicle's
    journey appears to take a third of the time it really did and the gate
    rejects the match as physically impossible.
    """
    with VideoSource(ten_frame_video, epoch_at, strided_settings) as source:
        stamps = [stamp for _, stamp in source.frames()]

    assert stamps == [
        "2026-01-01T00:00:00.000Z",  # frame 0
        "2026-01-01T00:00:00.300Z",  # frame 3, not 0.100
        "2026-01-01T00:00:00.600Z",  # frame 6, not 0.200
        "2026-01-01T00:00:00.900Z",  # frame 9, not 0.300
    ]


def test_stride_changes_which_frames_are_yielded_not_their_spacing(
    ten_frame_video: Path,
    strided_settings: Settings,
    epoch_at: datetime,
) -> None:
    """Consecutive kept frames sit STRIDE/fps apart, not 1/fps apart."""
    with VideoSource(ten_frame_video, epoch_at, strided_settings) as source:
        stamps = [stamp for _, stamp in source.frames()]

    parsed = [datetime.fromisoformat(stamp.replace("Z", "+00:00")) for stamp in stamps]
    gaps_seconds = [
        (later - earlier).total_seconds() for earlier, later in zip(parsed, parsed[1:])
    ]

    expected_gap_seconds = strided_settings.FRAME_STRIDE / TEST_VIDEO_FPS
    assert gaps_seconds == pytest.approx([expected_gap_seconds] * len(gaps_seconds))


def test_stride_of_one_yields_every_frame(
    ten_frame_video: Path,
    tmp_path: Path,
    epoch_at: datetime,
) -> None:
    unstrided = Settings(
        FRAME_STRIDE=1,
        PLAYBACK_FPS=TEST_VIDEO_FPS,
        CROP_STORAGE_PATH=tmp_path / "crops",
    )

    with VideoSource(ten_frame_video, epoch_at, unstrided) as source:
        stamps = [stamp for _, stamp in source.frames()]

    assert len(stamps) == 10
    assert stamps[1] == "2026-01-01T00:00:00.100Z"


def test_two_workers_sharing_an_epoch_agree_on_frame_times(epoch_at: datetime) -> None:
    """The property the shared epoch exists to guarantee.

    Two cameras processing the same frame index must produce the same
    timestamp, regardless of when either actually decoded it.
    """
    camera_one = frame_timestamp(epoch_at, frame_index=45, fps=15.0)
    camera_two = frame_timestamp(epoch_at, frame_index=45, fps=15.0)

    assert camera_one == camera_two == "2026-01-01T00:00:03.000Z"


def test_naive_epoch_is_rejected() -> None:
    naive_epoch = datetime(2026, 1, 1, 0, 0, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        frame_timestamp(naive_epoch, frame_index=0, fps=10.0)


def test_non_positive_fps_is_rejected(epoch_at: datetime) -> None:
    with pytest.raises(ValueError, match="fps must be positive"):
        frame_timestamp(epoch_at, frame_index=0, fps=0.0)


def test_iso_format_carries_a_z_suffix(epoch_at: datetime) -> None:
    """schema.md section 2 requires ISO-8601 UTC with Z, not +00:00."""
    stamp = to_iso8601_utc(epoch_at + timedelta(seconds=1.5))

    assert stamp.endswith("Z")
    assert "+00:00" not in stamp


def test_non_utc_input_is_converted_not_relabelled() -> None:
    """A tz-aware non-UTC datetime must be shifted, not stamped with Z as-is."""
    plus_five_thirty = timezone(timedelta(hours=5, minutes=30))
    ist_moment = datetime(2026, 1, 1, 5, 30, 0, tzinfo=plus_five_thirty)

    assert to_iso8601_utc(ist_moment) == "2026-01-01T00:00:00.000Z"
