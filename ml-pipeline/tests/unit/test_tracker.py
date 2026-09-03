"""Tracklet lifecycle: when a track finalises, and when it is discarded.

These exercise TrackletBuffer directly. It carries no Ultralytics dependency, so
the lifecycle rules are tested as the arithmetic they are, with no model load
and no video decode (rules.md section 6: no model loading in unit tests).
"""

from __future__ import annotations

import numpy as np
import pytest

from src.config import Settings
from src.tracker import TrackletBuffer
from src.types import Detection, Tracklet

CAMERA_ID = "CAM-01"
FRAME_HEIGHT_PX = 240
FRAME_WIDTH_PX = 320


def make_frame() -> np.ndarray:
    """A frame with structure, so crops have a non-degenerate Laplacian variance."""
    rng = np.random.default_rng(seed=1234)
    return rng.integers(
        0, 256, size=(FRAME_HEIGHT_PX, FRAME_WIDTH_PX, 3), dtype=np.uint8
    )


def make_detection(class_name: str = "car", class_id: int = 2) -> Detection:
    return Detection(
        bbox_x_px=10,
        bbox_y_px=10,
        bbox_w_px=40,
        bbox_h_px=40,
        det_conf=0.9,
        class_id=class_id,
        class_name=class_name,
    )


def feed_frames(
    buffer: TrackletBuffer,
    track_ids: list[int],
    frame_count: int,
    start_index: int = 0,
) -> list[Tracklet]:
    """Feed `frame_count` frames in which every id in `track_ids` is observed."""
    frame = make_frame()
    finalised: list[Tracklet] = []

    for offset in range(frame_count):
        frame_index = start_index + offset
        observations = [(track_id, make_detection()) for track_id in track_ids]
        finalised.extend(
            buffer.update(
                observations,
                frame,
                f"2026-01-01T00:00:{frame_index:02d}.000Z",
                frame_index,
            )
        )

    return finalised


def test_track_absent_for_lost_frames_finalises_exactly_once(
    lifecycle_settings: Settings,
) -> None:
    """The central lifecycle guarantee: one tracklet per track, not zero or many.

    A track re-finalising on every subsequent frame would emit duplicate
    sightings of one vehicle, which the backend would resolve into a phantom
    trajectory doubling back on itself.
    """
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)

    # Six frames of track 1: comfortably past TRACKLET_MIN_FRAMES of 4.
    during = feed_frames(buffer, track_ids=[1], frame_count=6)
    assert during == [], "a live track must not finalise"

    # Now let it lapse. TRACK_LOST_FRAMES is 3, so the third absent frame
    # finalises it. Run well past that to prove it does not fire again.
    absent = feed_frames(buffer, track_ids=[], frame_count=10, start_index=6)

    assert len(absent) == 1
    assert absent[0].track_id == 1
    assert absent[0].camera_id == CAMERA_ID
    assert absent[0].frame_count == 6
    assert buffer.open_track_ids == set()


def test_finalisation_does_not_fire_before_lost_frames_elapse(
    lifecycle_settings: Settings,
) -> None:
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)
    feed_frames(buffer, track_ids=[1], frame_count=6)

    # Two absent frames, one short of TRACK_LOST_FRAMES=3.
    finalised = feed_frames(buffer, track_ids=[], frame_count=2, start_index=6)

    assert finalised == []
    assert buffer.open_track_ids == {1}


def test_tracklet_under_min_frames_is_discarded(
    lifecycle_settings: Settings,
) -> None:
    """A three-frame track is detector noise and must not become a sighting.

    TRACKLET_MIN_FRAMES is 4 here, so three frames is one short.
    """
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)

    feed_frames(buffer, track_ids=[7], frame_count=3)
    finalised = feed_frames(buffer, track_ids=[], frame_count=6, start_index=3)

    assert finalised == []
    assert buffer.open_track_ids == set(), "a discarded track must still be released"


def test_discarded_short_track_is_not_retried_on_later_frames(
    lifecycle_settings: Settings,
) -> None:
    """A track dropped for being short must be forgotten, not re-tested forever."""
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)
    feed_frames(buffer, track_ids=[7], frame_count=3)

    feed_frames(buffer, track_ids=[], frame_count=4, start_index=3)
    later = feed_frames(buffer, track_ids=[], frame_count=20, start_index=7)

    assert later == []


def test_tracklet_at_exactly_min_frames_survives(lifecycle_settings: Settings) -> None:
    """TRACKLET_MIN_FRAMES is inclusive: exactly four frames is enough."""
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)

    feed_frames(buffer, track_ids=[3], frame_count=4)
    finalised = feed_frames(buffer, track_ids=[], frame_count=5, start_index=4)

    assert len(finalised) == 1
    assert finalised[0].frame_count == 4


def test_concurrent_tracks_finalise_independently(
    lifecycle_settings: Settings,
) -> None:
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)

    feed_frames(buffer, track_ids=[1, 2], frame_count=5)
    # Track 2 leaves; track 1 stays visible.
    finalised = feed_frames(buffer, track_ids=[1], frame_count=5, start_index=5)

    assert [tracklet.track_id for tracklet in finalised] == [2]
    assert buffer.open_track_ids == {1}


def test_flush_finalises_tracks_still_open_at_end_of_stream(
    lifecycle_settings: Settings,
) -> None:
    """A clip ending is not the same as a track lapsing."""
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)
    feed_frames(buffer, track_ids=[1], frame_count=6)

    flushed = buffer.flush()

    assert len(flushed) == 1
    assert flushed[0].track_id == 1
    assert buffer.open_track_ids == set()


def test_flush_still_discards_short_tracks(lifecycle_settings: Settings) -> None:
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)
    feed_frames(buffer, track_ids=[1], frame_count=2)

    assert buffer.flush() == []


def test_tracklet_timestamps_span_first_to_last_sample(
    lifecycle_settings: Settings,
) -> None:
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)
    feed_frames(buffer, track_ids=[1], frame_count=5)

    flushed = buffer.flush()

    assert flushed[0].first_frame_at == "2026-01-01T00:00:00.000Z"
    assert flushed[0].last_frame_at == "2026-01-01T00:00:04.000Z"


def test_coco_class_name_survives_into_the_tracklet(
    lifecycle_settings: Settings,
) -> None:
    """The backend gates matches on vehicle class, so the label must persist."""
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)
    frame = make_frame()

    for frame_index in range(5):
        buffer.update(
            [(1, make_detection(class_name="truck", class_id=7))],
            frame,
            f"2026-01-01T00:00:{frame_index:02d}.000Z",
            frame_index,
        )

    tracklet = buffer.flush()[0]

    assert {sample.detection.class_name for sample in tracklet.samples} == {"truck"}


def test_buffered_crop_does_not_alias_the_source_frame(
    lifecycle_settings: Settings,
) -> None:
    """Crops must be copies, or every decoded frame stays pinned in memory.

    A numpy slice is a view onto the whole frame. Buffering views would hold the
    entire clip resident until its tracklets finalised, and would also let a
    later frame's pixels appear in an earlier frame's crop.
    """
    buffer = TrackletBuffer(CAMERA_ID, lifecycle_settings)
    frame = make_frame()

    for frame_index in range(5):
        buffer.update(
            [(1, make_detection())],
            frame,
            f"2026-01-01T00:00:{frame_index:02d}.000Z",
            frame_index,
        )

    tracklet = buffer.flush()[0]
    first_crop = tracklet.samples[0].crop_bgr
    before = first_crop.copy()

    frame[:] = 0

    assert np.array_equal(first_crop, before), "crop aliases the frame buffer"


def test_crops_below_min_area_are_not_buffered_but_keep_the_track_alive(
    tmp_path: object,
) -> None:
    """A vehicle too small to be a best-shot candidate is still present.

    Treating it as absent would split one vehicle's pass into two tracklets.
    """
    settings = Settings(
        TRACK_LOST_FRAMES=3,
        TRACKLET_MIN_FRAMES=1,
        BEST_SHOT_MIN_AREA_PX=10_000,
        CROP_STORAGE_PATH=tmp_path / "crops",  # type: ignore[operator]
    )
    buffer = TrackletBuffer(CAMERA_ID, settings)
    frame = make_frame()

    # 40x40 = 1600 px, well under the 10,000 px floor.
    for frame_index in range(5):
        buffer.update(
            [(1, make_detection())],
            frame,
            f"2026-01-01T00:00:{frame_index:02d}.000Z",
            frame_index,
        )

    assert buffer.open_track_ids == {1}, "track must stay open despite tiny crops"
    assert buffer.flush() == [], "no samples buffered, so nothing to finalise"
