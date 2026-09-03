"""Tracklet lifecycle: buffering per-frame crops and finalising completed tracks.

THE TWO-TIER RULE
-----------------
Tier 1, per frame, is this module and `detector.py`: detect, associate, append a
crop plus its metadata to the open track's buffer. Nothing else.

Tier 2, per *tracklet finalisation*, is best-shot selection followed by OCR and
embedding. It happens downstream of the generator this module yields.

Nothing in this file calls an embedder or an OCR engine, and nothing in this
file may ever be changed to. A 20-second clip at 15 fps carries roughly 300
frames; running a Re-ID forward pass per detection per frame across a handful of
tracks is on the order of 50,000 forward passes for the same clip that
tier-2-only work completes in a few hundred. That difference is the whole
pipeline budget.

The module is split so that the lifecycle rules — when a track finalises, when
one is discarded — live in `TrackletBuffer`, which has no Ultralytics dependency
and can be tested directly. `VehicleTracker` binds that buffer to the detector
and the video source.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from src.best_shot import laplacian_variance
from src.config import Settings, get_settings
from src.detector import VehicleDetector
from src.types import Detection, FrameSample, Tracklet
from src.video_source import VideoSource


@dataclass
class _OpenTrack:
    """Mutable accumulator for a track that is still being observed.

    This is the one deliberately mutable structure in the pipeline. `Tracklet`
    is frozen; an open track is not a tracklet yet, and modelling it as one
    would mean rebuilding an immutable object on every frame of every track.
    """

    track_id: int
    samples: list[FrameSample] = field(default_factory=list)
    last_seen_frame_index: int = 0


class TrackletBuffer:
    """Holds open tracks and finalises them once their id goes absent.

    A track is finalised when it has not been observed for TRACK_LOST_FRAMES
    *processed* frames. The count is in processed frames, so it is already
    expressed post-FRAME_STRIDE and needs no stride correction.
    """

    def __init__(self, camera_id: str, settings: Settings | None = None) -> None:
        """Create a buffer for one camera.

        Args:
            camera_id: Camera this buffer belongs to; stamped onto every Tracklet.
            settings: Pipeline settings; the process singleton when omitted.
        """
        self._settings = settings if settings is not None else get_settings()
        self._camera_id = camera_id
        self._open_tracks: dict[int, _OpenTrack] = {}
        self._processed_frame_count = 0

    @property
    def open_track_ids(self) -> set[int]:
        """Track ids currently held open."""
        return set(self._open_tracks)

    def update(
        self,
        observations: list[tuple[int, Detection]],
        frame_bgr: np.ndarray,
        frame_at: str,
        frame_index: int,
    ) -> list[Tracklet]:
        """Buffer this frame's observations and finalise any lapsed tracks.

        Args:
            observations: (track_id, Detection) pairs for this frame.
            frame_bgr: The decoded BGR frame the detections came from.
            frame_at: ISO-8601 UTC timestamp of the frame.
            frame_index: True decode index of the frame, for timestamping.

        Returns:
            Tracklets finalised on this frame, already filtered by
            TRACKLET_MIN_FRAMES. Usually empty.
        """
        self._processed_frame_count += 1

        for track_id, detection in observations:
            open_track = self._open_tracks.get(track_id)
            if open_track is None:
                open_track = _OpenTrack(track_id=track_id)
                self._open_tracks[track_id] = open_track

            # Mark the track alive before any decision about keeping the crop:
            # a vehicle too small to be worth a best-shot candidate is still
            # present, and letting it look absent would split one tracklet in two.
            open_track.last_seen_frame_index = self._processed_frame_count

            sample = self._build_sample(detection, frame_bgr, frame_at, frame_index)
            if sample is not None:
                open_track.samples.append(sample)

        return self._finalise_lapsed()

    def _build_sample(
        self,
        detection: Detection,
        frame_bgr: np.ndarray,
        frame_at: str,
        frame_index: int,
    ) -> FrameSample | None:
        """Crop one detection out of the frame and measure its sharpness.

        Returns None for crops below BEST_SHOT_MIN_AREA_PX, which are too small
        to serve as a best shot and would only cost memory.
        """
        if detection.area_px < self._settings.BEST_SHOT_MIN_AREA_PX:
            return None

        frame_height_px, frame_width_px = frame_bgr.shape[:2]

        # Clamp to the frame: YOLO boxes can extend past the edge, and a
        # negative slice bound silently produces an empty or wrapped crop.
        x1 = max(0, detection.bbox_x_px)
        y1 = max(0, detection.bbox_y_px)
        x2 = min(frame_width_px, detection.bbox_x_px + detection.bbox_w_px)
        y2 = min(frame_height_px, detection.bbox_y_px + detection.bbox_h_px)
        if x2 <= x1 or y2 <= y1:
            return None

        # .copy() is required, not defensive habit: a numpy slice is a view onto
        # the whole frame, so buffering views would pin every decoded frame of
        # the clip in memory until its tracklet finalised.
        crop_bgr = frame_bgr[y1:y2, x1:x2].copy()

        return FrameSample(
            crop_bgr=crop_bgr,
            frame_at=frame_at,
            frame_index=frame_index,
            detection=detection,
            area_px=detection.area_px,
            det_conf=detection.det_conf,
            blur_var=laplacian_variance(crop_bgr),
        )

    def _finalise_lapsed(self) -> list[Tracklet]:
        """Finalise every open track absent for TRACK_LOST_FRAMES."""
        lost_frames = self._settings.TRACK_LOST_FRAMES
        lapsed_ids = [
            track_id
            for track_id, open_track in self._open_tracks.items()
            if self._processed_frame_count - open_track.last_seen_frame_index >= lost_frames
        ]

        finalised: list[Tracklet] = []
        for track_id in lapsed_ids:
            # Popped before the length test, so a track that lapses while too
            # short is removed rather than re-finalised on every later frame.
            # This is what makes finalisation happen exactly once per track.
            open_track = self._open_tracks.pop(track_id)
            tracklet = self._to_tracklet(open_track)
            if tracklet is not None:
                finalised.append(tracklet)

        return finalised

    def flush(self) -> list[Tracklet]:
        """Finalise all remaining open tracks at end of stream.

        Returns:
            Every surviving tracklet, filtered by TRACKLET_MIN_FRAMES.
        """
        finalised: list[Tracklet] = []
        for track_id in list(self._open_tracks):
            open_track = self._open_tracks.pop(track_id)
            tracklet = self._to_tracklet(open_track)
            if tracklet is not None:
                finalised.append(tracklet)
        return finalised

    def _to_tracklet(self, open_track: _OpenTrack) -> Tracklet | None:
        """Freeze an open track, or discard it as too short.

        Returns None when the track carries fewer than TRACKLET_MIN_FRAMES
        samples. Short tracks are detector noise — a vehicle glimpsed across
        three frames yields a crop too marginal to embed reliably, and admitting
        it costs a spurious identity in the backend.
        """
        if len(open_track.samples) < self._settings.TRACKLET_MIN_FRAMES:
            return None

        samples = tuple(open_track.samples)
        return Tracklet(
            track_id=open_track.track_id,
            camera_id=self._camera_id,
            samples=samples,
            first_frame_at=samples[0].frame_at,
            last_frame_at=samples[-1].frame_at,
        )


class VehicleTracker:
    """Binds the detector and the tracklet buffer to a video source."""

    def __init__(
        self,
        camera_id: str,
        detector: VehicleDetector,
        settings: Settings | None = None,
    ) -> None:
        """Create a tracker for one camera.

        Args:
            camera_id: Camera being processed.
            detector: The loaded YOLOv8s detector.
            settings: Pipeline settings; the process singleton when omitted.
        """
        self._settings = settings if settings is not None else get_settings()
        self._detector = detector
        self._buffer = TrackletBuffer(camera_id, self._settings)

    def tracklets(self, source: VideoSource) -> Iterator[Tracklet]:
        """Yield finalised tracklets as the video is consumed.

        A generator by design. Tier-2 work is expensive, and yielding each
        tracklet as it completes lets the caller process and release it while
        the rest of the clip is still decoding. Accumulating every tracklet
        first would hold every buffered crop of the whole clip in memory at once.

        Args:
            source: An open VideoSource for this camera.

        Yields:
            Tracklets in completion order, each already past TRACKLET_MIN_FRAMES.
        """
        frame_index = 0

        for frame_bgr, frame_at in source.frames():
            observations = self._detector.track(frame_bgr)
            yield from self._buffer.update(observations, frame_bgr, frame_at, frame_index)
            frame_index += 1

        # The clip ending is not the same as every track lapsing: tracks still
        # open on the last frame would otherwise be silently dropped.
        yield from self._buffer.flush()
