"""Plate ROI construction: the width ceiling and the OCR crop budget.

These exercise ROI geometry and crop selection, not OCR accuracy. The EasyOCR
Reader is built once for the module because construction costs seconds.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.config import Settings
from src.plate_reader import PlateReader
from src.types import Detection, FrameSample


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(
        PLATE_ROI_FRACTION=0.40,
        PLATE_UPSCALE_FACTOR=4,
        PLATE_ROI_MAX_WIDTH_PX=640,
        PLATE_OCR_TOP_K=3,
        CROP_STORAGE_PATH=Path("/tmp/marg-plate-tests"),
    )


@pytest.fixture(scope="module")
def reader(settings: Settings) -> PlateReader:
    return PlateReader(settings)


def make_crop(width_px: int, height_px: int) -> np.ndarray:
    rng = np.random.default_rng(seed=width_px)
    return rng.integers(0, 256, size=(height_px, width_px, 3), dtype=np.uint8)


def make_sample(width_px: int, det_conf: float = 0.9) -> FrameSample:
    crop = make_crop(width_px, width_px)
    detection = Detection(
        bbox_x_px=0,
        bbox_y_px=0,
        bbox_w_px=width_px,
        bbox_h_px=width_px,
        det_conf=det_conf,
        class_id=2,
        class_name="car",
    )
    return FrameSample(
        crop_bgr=crop,
        frame_at="2026-01-01T00:00:00.000Z",
        frame_index=0,
        detection=detection,
        area_px=detection.area_px,
        det_conf=det_conf,
        blur_var=100.0,
    )


def test_small_plate_still_gets_the_full_upscale(reader: PlateReader) -> None:
    """The ceiling must not penalise distant vehicles, which need the upscale most."""
    roi, scale = reader._roi_with_scale(make_crop(80, 60))

    assert scale == pytest.approx(4.0)
    assert roi.shape[1] == 320


def test_roi_exactly_at_the_ceiling_is_not_reduced(reader: PlateReader) -> None:
    """160 px upscaled 4x is exactly 640, the ceiling. It must pass untouched."""
    roi, scale = reader._roi_with_scale(make_crop(160, 120))

    assert scale == pytest.approx(4.0)
    assert roi.shape[1] == 640


def test_frame_filling_vehicle_is_clamped(reader: PlateReader) -> None:
    """The case this change exists for: 640x480 would otherwise reach 2560 px."""
    roi, scale = reader._roi_with_scale(make_crop(640, 480))

    assert roi.shape[1] == 640
    assert scale == pytest.approx(1.0)


def test_clamp_preserves_aspect_ratio(reader: PlateReader) -> None:
    crop = make_crop(1240, 1030)
    roi_height_px = crop.shape[0] - int(crop.shape[0] * (1.0 - 0.40))

    roi, scale = reader._roi_with_scale(crop)

    assert roi.shape[1] == 640
    expected_height_px = round(roi_height_px * scale)
    assert abs(roi.shape[0] - expected_height_px) <= 1


def test_clamped_roi_never_exceeds_the_ceiling(reader: PlateReader) -> None:
    for width_px in (200, 400, 800, 1600, 3000):
        roi, _ = reader._roi_with_scale(make_crop(width_px, width_px))

        assert roi.shape[1] <= 640, f"width {width_px} produced {roi.shape[1]} px"


def test_extract_plate_roi_matches_the_scaled_variant(reader: PlateReader) -> None:
    crop = make_crop(300, 200)

    assert np.array_equal(reader.extract_plate_roi(crop), reader._roi_with_scale(crop)[0])


def test_empty_crop_is_returned_unchanged(reader: PlateReader) -> None:
    empty = np.empty((0, 0, 3), dtype=np.uint8)

    roi, scale = reader._roi_with_scale(empty)

    assert roi.size == 0
    assert scale == 1.0


def test_only_top_k_crops_are_sent_to_ocr(
    reader: PlateReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PLATE_OCR_TOP_K bounds OCR calls independently of BEST_SHOT_TOP_K."""
    call_count = 0

    def counting_read_one(_crop: np.ndarray) -> None:
        nonlocal call_count
        call_count += 1
        return None

    monkeypatch.setattr(reader, "_read_one", counting_read_one)

    best_shots = tuple(make_sample(100) for _ in range(8))
    reader.read_tracklet(best_shots)

    assert call_count == 3


def test_fewer_shots_than_top_k_reads_all_of_them(
    reader: PlateReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0

    def counting_read_one(_crop: np.ndarray) -> None:
        nonlocal call_count
        call_count += 1
        return None

    monkeypatch.setattr(reader, "_read_one", counting_read_one)

    reader.read_tracklet(tuple(make_sample(100) for _ in range(2)))

    assert call_count == 2


def test_ocr_budget_takes_the_strongest_shots(
    reader: PlateReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """best_shots arrives best-first, so the budget must take the head."""
    seen_widths: list[int] = []

    def recording_read_one(crop: np.ndarray) -> None:
        seen_widths.append(crop.shape[1])
        return None

    monkeypatch.setattr(reader, "_read_one", recording_read_one)

    ordered = (make_sample(300), make_sample(200), make_sample(100), make_sample(50))
    reader.read_tracklet(ordered)

    assert seen_widths == [300, 200, 100]


def test_unreadable_tracklet_returns_the_empty_result(
    reader: PlateReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reader, "_read_one", lambda _crop: None)

    result = reader.read_tracklet((make_sample(100),))

    assert result.text_norm is None
    assert result.is_valid is False
