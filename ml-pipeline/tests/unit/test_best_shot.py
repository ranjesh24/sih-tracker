"""Best-shot scoring, and specifically the blur term's veto.

The load-bearing case is a sharp small crop beating a blurred large one. Without
the Laplacian term, area and confidence alone would select the blurriest large
crop of every fast-moving vehicle — precisely the crop OCR and Re-ID handle worst.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.best_shot import laplacian_variance, select_best_shots, shot_score
from src.config import Settings
from src.types import Detection, FrameSample


def make_sharp_crop(size_px: int) -> np.ndarray:
    """Random noise: maximal high-frequency content, so a high Laplacian variance."""
    rng = np.random.default_rng(seed=7)
    return rng.integers(0, 256, size=(size_px, size_px, 3), dtype=np.uint8)


def make_blurred_crop(size_px: int) -> np.ndarray:
    """The same noise, heavily blurred. Large, but with its edges destroyed."""
    blurred = cv2.GaussianBlur(make_sharp_crop(size_px), (31, 31), sigmaX=15.0)
    return blurred


def make_sample(crop_bgr: np.ndarray, det_conf: float = 0.9) -> FrameSample:
    """Wrap a crop as a FrameSample, measuring blur with the real function."""
    height_px, width_px = crop_bgr.shape[:2]
    detection = Detection(
        bbox_x_px=0,
        bbox_y_px=0,
        bbox_w_px=width_px,
        bbox_h_px=height_px,
        det_conf=det_conf,
        class_id=2,
        class_name="car",
    )
    return FrameSample(
        crop_bgr=crop_bgr,
        frame_at="2026-01-01T00:00:00.000Z",
        frame_index=0,
        detection=detection,
        area_px=detection.area_px,
        det_conf=det_conf,
        blur_var=laplacian_variance(crop_bgr),
    )


@pytest.fixture
def default_settings(tmp_path: Path) -> Settings:
    return Settings(BEST_SHOT_TOP_K=5, CROP_STORAGE_PATH=tmp_path / "crops")


def test_sharp_small_crop_outranks_blurred_large_crop(
    default_settings: Settings,
) -> None:
    """The test the blur term exists for.

    The blurred crop is 16x the area and carries identical detection
    confidence, so area and confidence both favour it. Only the Laplacian term
    can overturn that, and it must.
    """
    sharp_small = make_sample(make_sharp_crop(60))
    blurred_large = make_sample(make_blurred_crop(240))

    assert blurred_large.area_px == 16 * sharp_small.area_px
    assert blurred_large.det_conf == sharp_small.det_conf

    ranked = select_best_shots((blurred_large, sharp_small), default_settings)

    assert ranked[0] is sharp_small
    assert ranked[1] is blurred_large


def test_blur_variance_separates_sharp_from_blurred() -> None:
    sharp_variance = laplacian_variance(make_sharp_crop(120))
    blurred_variance = laplacian_variance(make_blurred_crop(120))

    assert sharp_variance > blurred_variance


def test_score_is_the_product_of_all_three_terms() -> None:
    sample = make_sample(make_sharp_crop(50), det_conf=0.8)

    expected = float(sample.area_px) * sample.det_conf * sample.blur_var

    assert shot_score(sample) == pytest.approx(expected)


def test_results_are_ordered_highest_score_first(default_settings: Settings) -> None:
    samples = tuple(make_sample(make_sharp_crop(size)) for size in (40, 100, 70))

    ranked = select_best_shots(samples, default_settings)
    scores = [shot_score(sample) for sample in ranked]

    assert scores == sorted(scores, reverse=True)


def test_returns_at_most_top_k(tmp_path: Path) -> None:
    settings = Settings(BEST_SHOT_TOP_K=3, CROP_STORAGE_PATH=tmp_path / "crops")
    samples = tuple(make_sample(make_sharp_crop(40 + step * 10)) for step in range(8))

    ranked = select_best_shots(samples, settings)

    assert len(ranked) == 3


def test_returns_all_when_fewer_than_top_k(default_settings: Settings) -> None:
    samples = tuple(make_sample(make_sharp_crop(size)) for size in (40, 60))

    assert len(select_best_shots(samples, default_settings)) == 2


def test_empty_input_returns_empty(default_settings: Settings) -> None:
    assert select_best_shots((), default_settings) == ()


def test_selection_does_not_mutate_its_input(default_settings: Settings) -> None:
    """A pure function: the caller's tuple must be untouched."""
    samples = tuple(make_sample(make_sharp_crop(size)) for size in (40, 100, 70))
    original_order = list(samples)

    select_best_shots(samples, default_settings)

    assert list(samples) == original_order


def test_zero_confidence_detection_scores_zero() -> None:
    """Each term vetoes independently; that is why the score is a product."""
    sample = make_sample(make_sharp_crop(80), det_conf=0.0)

    assert shot_score(sample) == 0.0


def test_empty_crop_has_zero_blur_variance() -> None:
    assert laplacian_variance(np.empty((0, 0, 3), dtype=np.uint8)) == 0.0
