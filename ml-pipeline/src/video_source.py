"""Video decoding and frame timestamping.

The timestamp rule, which is the whole reason this module exists
--------------------------------------------------------------
A frame's timestamp is derived arithmetically from its index:

    frame_at = epoch_at + (frame_index / fps)

It is never `datetime.now()` at the moment the frame was decoded. Decode speed
varies with GPU load, disk contention and how many workers are running, so
wall-clock timestamping makes a frame's recorded time depend on how busy the
machine was. Two workers decoding the same synthetic minute would then disagree
about when their vehicles were seen.

That divergence does not present as a timing bug. It presents as a *matching*
bug: the backend's spatio-temporal gate compares `first_frame_at` across
cameras, and skewed clocks make genuinely feasible transits look impossible, so
the gate emits TEMPORAL_TOO_FAST rejections for correct matches. Someone then
spends an evening debugging the resolver, which is not where the fault is.
`received_at` on the sightings table exists solely to detect this
(schema.md section 3.6).

All workers are handed the same `epoch_at`, so their synthetic clocks share an
origin and the arithmetic keeps them aligned for the length of the run.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType

import cv2
import numpy as np

from src.config import Settings, get_settings


class VideoSourceError(RuntimeError):
    """Raised when a video cannot be opened or carries an unusable frame rate."""


def to_iso8601_utc(moment: datetime) -> str:
    """Format a timezone-aware datetime as ISO-8601 UTC with a `Z` suffix.

    Args:
        moment: A timezone-aware datetime. Naive datetimes are rejected.

    Returns:
        An ISO-8601 string ending in `Z`, matching the timestamp convention in
        schema.md section 2 (lexicographic order equals chronological order).

    Raises:
        ValueError: If `moment` is naive.
    """
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware UTC, got a naive datetime")
    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def frame_timestamp(epoch_at: datetime, frame_index: int, fps: float) -> str:
    """Compute the ISO-8601 UTC timestamp of one frame from its index.

    This is the arithmetic the module docstring describes. It is a free function
    so it can be tested without opening a video file.

    Args:
        epoch_at: Shared synthetic start time, timezone-aware UTC. Every worker
            in a run receives the same value.
        frame_index: Zero-based index of the frame in the source, counting every
            decoded frame including those skipped by FRAME_STRIDE.
        fps: Frames per second of the source.

    Returns:
        ISO-8601 UTC string with a `Z` suffix.

    Raises:
        ValueError: If `fps` is not positive or `frame_index` is negative.
    """
    if fps <= 0.0:
        raise ValueError(f"fps must be positive, got {fps}")
    if frame_index < 0:
        raise ValueError(f"frame_index must be non-negative, got {frame_index}")

    offset_seconds = frame_index / fps
    return to_iso8601_utc(epoch_at + timedelta(seconds=offset_seconds))


class VideoSource:
    """A cv2.VideoCapture wrapper yielding (frame, ISO-8601 timestamp) pairs.

    Frames are decoded sequentially and FRAME_STRIDE selects which of them are
    yielded. Skipping is done by decoding and discarding rather than by seeking
    with CAP_PROP_POS_FRAMES, because seeking is unreliable on the long-GOP
    codecs typical of CCTV footage and silently lands on the wrong frame.

    Crucially, skipping changes only *which* frames come out. The frame index
    driving the timestamp still counts every decoded frame, so with
    FRAME_STRIDE=3 the yielded frames are 0, 3, 6 ... and their timestamps are
    epoch+0/fps, epoch+3/fps, epoch+6/fps — not epoch+0, epoch+1/fps, epoch+2/fps.
    Getting that wrong compresses the synthetic clock by the stride factor and
    reintroduces exactly the gate failure this module exists to prevent.
    """

    def __init__(
        self,
        video_path: Path,
        epoch_at: datetime,
        settings: Settings | None = None,
    ) -> None:
        """Open a video and resolve its frame rate.

        Args:
            video_path: Path to the source video.
            epoch_at: Shared synthetic start time, timezone-aware UTC.
            settings: Pipeline settings; the process singleton when omitted.

        Raises:
            VideoSourceError: If the file is missing or cannot be opened.
            ValueError: If `epoch_at` is naive.
        """
        self._settings = settings if settings is not None else get_settings()

        if epoch_at.tzinfo is None:
            raise ValueError("epoch_at must be timezone-aware UTC, got a naive datetime")
        self._epoch_at = epoch_at

        # Fail at startup, not on frame 400 (rules.md R3).
        if not video_path.is_file():
            raise VideoSourceError(f"video not found: {video_path}")

        self._video_path = video_path
        self._capture = cv2.VideoCapture(str(video_path))
        if not self._capture.isOpened():
            raise VideoSourceError(f"could not open video: {video_path}")

        self._fps = self._resolve_fps()
        self._frame_index = 0

    def _resolve_fps(self) -> float:
        """Return the source frame rate, falling back to PLAYBACK_FPS.

        The container's declared rate is preferred because it is a property of
        the footage rather than a tunable. Some CCTV exports report 0 or NaN, in
        which case the configured PLAYBACK_FPS stands in.
        """
        declared_fps = self._capture.get(cv2.CAP_PROP_FPS)
        if declared_fps is None or not math.isfinite(declared_fps) or declared_fps <= 0.0:
            return self._settings.PLAYBACK_FPS
        return float(declared_fps)

    @property
    def fps(self) -> float:
        """Frame rate used for timestamp arithmetic."""
        return self._fps

    @property
    def video_path(self) -> Path:
        """Path of the open source video."""
        return self._video_path

    def frames(self) -> Iterator[tuple[np.ndarray, str]]:
        """Yield (frame, timestamp) for every FRAME_STRIDE-th decoded frame.

        Yields:
            Pairs of the decoded BGR frame and its ISO-8601 UTC timestamp,
            computed from the true decode index regardless of stride.
        """
        stride = self._settings.FRAME_STRIDE

        while True:
            is_read, frame = self._capture.read()
            if not is_read:
                return

            current_index = self._frame_index
            self._frame_index += 1

            if current_index % stride != 0:
                continue

            yield frame, frame_timestamp(self._epoch_at, current_index, self._fps)

    def close(self) -> None:
        """Release the underlying capture."""
        self._capture.release()

    def __enter__(self) -> VideoSource:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
