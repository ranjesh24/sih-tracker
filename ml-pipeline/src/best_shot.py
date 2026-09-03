"""Best-shot selection: choosing which buffered crops are worth tier-2 work.

This is the hinge between the two tiers. Tier 1 buffers every crop of a track;
tier 2 runs OCR and a Re-ID embedding, which are expensive. Selecting the few
best crops per tracklet is what keeps the pipeline's cost proportional to the
number of *vehicles* rather than the number of *frames*.

The score is a product of three independent quality signals:

    score = area_px * det_conf * laplacian_variance

Each term vetoes on its own, which is the point of multiplying rather than
summing: a crop that is worthless on any one axis scores near zero regardless of
how it does on the other two.

  area_px               resolution actually available to OCR and the embedder
  det_conf              the detector's own confidence that this is a vehicle
  laplacian_variance    focus. This is the term that earns its place: a vehicle
                        close to the camera produces a large, high-confidence
                        crop that is also motion-blurred into uselessness. Area
                        and confidence both rate it highly. Only the blur term
                        rejects it, so dropping that term systematically selects
                        the blurriest large crop of every fast-moving vehicle.
"""

from __future__ import annotations

import cv2
import numpy as np

from src.config import Settings, get_settings
from src.types import FrameSample


def laplacian_variance(crop_bgr: np.ndarray) -> float:
    """Measure focus as the variance of the Laplacian of a crop.

    A sharp image has strong second derivatives at its edges and therefore a
    high Laplacian variance; blurring attenuates exactly those edges and
    collapses the variance. This is cheap enough to run per buffered crop in
    tier 1 — it is a single convolution, not a forward pass.

    Args:
        crop_bgr: A BGR crop. Empty crops score 0.0.

    Returns:
        Variance of the Laplacian. Higher is sharper. Not normalised: the value
        is meaningful only in comparison with other crops of the same scene.
    """
    if crop_bgr.size == 0:
        return 0.0

    grayscale = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(grayscale, cv2.CV_64F).var())


def shot_score(sample: FrameSample) -> float:
    """Score one buffered sample for tier-2 suitability.

    Args:
        sample: A buffered FrameSample, with its metrics already measured.

    Returns:
        The product of area, detection confidence and Laplacian variance.
    """
    return float(sample.area_px) * sample.det_conf * sample.blur_var


def select_best_shots(
    samples: tuple[FrameSample, ...],
    settings: Settings | None = None,
) -> tuple[FrameSample, ...]:
    """Return the highest-scoring samples of a tracklet, best first.

    A pure function: it reads no state and mutates neither its argument nor the
    samples in it.

    Args:
        samples: Every buffered sample of one finalised tracklet.
        settings: Pipeline settings; the process singleton when omitted.

    Returns:
        At most BEST_SHOT_TOP_K samples ordered by descending score. Returns
        fewer when the tracklet holds fewer, and an empty tuple for no input.
    """
    if not samples:
        return ()

    resolved = settings if settings is not None else get_settings()

    ranked = sorted(samples, key=shot_score, reverse=True)
    return tuple(ranked[: resolved.BEST_SHOT_TOP_K])
