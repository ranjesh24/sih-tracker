"""Plate OCR over a tracklet's best-shot crops. Tier-2 work only.

Cost model
----------
This module runs once per *finalised tracklet*, over the BEST_SHOT_TOP_K crops
chosen by best_shot.py — never per frame. A 20-second clip at 15 fps holds
roughly 300 frames; reading every detection in every frame would be tens of
thousands of OCR invocations for the same handful of vehicles that top-K
resolves in a few dozen.

The EasyOCR Reader is built once and reused. Construction loads a detection and
a recognition network and takes seconds; a Reader built per call would dominate
the runtime of the entire pipeline.

Why read several crops rather than only the best one
-----------------------------------------------------
Best-shot ranks by area, detection confidence and focus. Those predict a good
*embedding* well, but only loosely predict a readable *plate*: the sharpest,
largest crop is often the one where the vehicle is closest and most angled, so
the plate is foreshortened. Reading more than one and keeping the
highest-confidence result that survives the normalizer materially raises the
read rate.

How many is PLATE_OCR_TOP_K, which is deliberately separate from
BEST_SHOT_TOP_K. The embedder consumes every best shot because embedding K
crops is a single batched forward pass; OCR is K sequential CPU calls, so its
marginal cost per crop is far higher and it is budgeted separately.

The ROI width is also capped at PLATE_ROI_MAX_WIDTH_PX. EasyOCR's cost scales
with pixel count, and a frame-filling vehicle upscaled by a pure multiplier
reaches roughly 2560 px wide. The cap is a ceiling rather than a resize: a small
distant plate never reaches it and still receives the full upscale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import cv2
import numpy as np

from src.config import Settings, get_settings
from src.normalizer import normalize_plate
from src.types import FrameSample


@dataclass(frozen=True, slots=True)
class PlateRead:
    """The outcome of reading one tracklet's plate.

    A tracklet with no readable plate yields an instance with `text_norm` None
    and `is_valid` False. That is the ordinary case, not an error: see the
    module docstring in normalizer.py.
    """

    text_raw: str | None
    text_norm: str | None
    confidence: float | None
    is_valid: bool
    # JSON "[x, y, w, h]" relative to the vehicle crop, per schema.md section
    # 3.6, or None when nothing was read.
    bbox_json: str | None
    plate_crop_bgr: np.ndarray | None = None

    @classmethod
    def unread(cls) -> PlateRead:
        """The empty result, for a tracklet whose plate was never readable."""
        return cls(
            text_raw=None,
            text_norm=None,
            confidence=None,
            is_valid=False,
            bbox_json=None,
            plate_crop_bgr=None,
        )


class PlateReader:
    """Reads plates from vehicle crops with a single shared EasyOCR Reader."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Build the OCR engine once.

        Args:
            settings: Pipeline settings; the process singleton when omitted.
        """
        self._settings = settings if settings is not None else get_settings()

        # Imported here rather than at module scope so that importing this
        # module stays cheap for callers that never read a plate, and so a
        # missing easyocr surfaces at worker startup with the other model loads.
        import easyocr

        # gpu=False deliberately. EasyOCR's GPU path expects CUDA; on this
        # machine there is none, and its MPS support is not reliable. Plate
        # reading is per-tracklet, so CPU is affordable here in a way it would
        # never be per-frame.
        self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    def _roi_with_scale(self, vehicle_crop_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        """Build the plate ROI and report the scale actually applied to it.

        The scale is returned rather than assumed because PLATE_ROI_MAX_WIDTH_PX
        can reduce it below PLATE_UPSCALE_FACTOR. Mapping the OCR box back onto
        the vehicle crop with the nominal factor instead of the effective one
        would place `plate_bbox` in the wrong position in the evidence panel.

        Args:
            vehicle_crop_bgr: A cropped vehicle in BGR.

        Returns:
            (roi, effective_scale). An empty input yields a scale of 1.0.
        """
        if vehicle_crop_bgr.size == 0:
            return vehicle_crop_bgr, 1.0

        crop_height_px = vehicle_crop_bgr.shape[0]
        roi_start_y_px = int(crop_height_px * (1.0 - self._settings.PLATE_ROI_FRACTION))
        roi = vehicle_crop_bgr[roi_start_y_px:, :]

        if roi.size == 0:
            return roi, 1.0

        roi_width_px = roi.shape[1]
        upscale = float(self._settings.PLATE_UPSCALE_FACTOR)
        upscaled_width_px = roi_width_px * upscale

        # A ceiling, not a resize. A small distant plate never reaches the limit
        # and keeps the full upscale; only a frame-filling vehicle is pulled back
        # down, and only as far as the ceiling.
        max_width_px = self._settings.PLATE_ROI_MAX_WIDTH_PX
        if upscaled_width_px > max_width_px:
            upscale = max_width_px / roi_width_px

        target_width_px = max(1, int(round(roi_width_px * upscale)))
        target_height_px = max(1, int(round(roi.shape[0] * upscale)))

        # INTER_CUBIC when enlarging: the recogniser is sensitive to edge
        # definition on small glyphs. INTER_AREA when the clamp forces a
        # reduction, which is the correct filter for downscaling.
        interpolation = cv2.INTER_CUBIC if upscale >= 1.0 else cv2.INTER_AREA
        resized = cv2.resize(
            roi, (target_width_px, target_height_px), interpolation=interpolation
        )
        return resized, upscale

    def extract_plate_roi(self, vehicle_crop_bgr: np.ndarray) -> np.ndarray:
        """Take the lower PLATE_ROI_FRACTION band of a vehicle crop, upscaled.

        The upscaled width is capped at PLATE_ROI_MAX_WIDTH_PX with aspect ratio
        preserved.

        Args:
            vehicle_crop_bgr: A cropped vehicle in BGR.

        Returns:
            The region of interest. Empty input is returned unchanged.
        """
        return self._roi_with_scale(vehicle_crop_bgr)[0]

    def _read_one(self, vehicle_crop_bgr: np.ndarray) -> tuple[str, float, list[int]] | None:
        """Run OCR on one vehicle crop and return its best raw region.

        Returns:
            (text, confidence, [x, y, w, h]) for the highest-confidence region,
            or None if OCR found no text. The bbox is expressed in the
            coordinates of the original vehicle crop, not the upscaled ROI.
        """
        roi, effective_scale = self._roi_with_scale(vehicle_crop_bgr)
        if roi.size == 0:
            return None

        regions = self._reader.readtext(roi)
        if not regions:
            return None

        best_bbox, best_text, best_confidence = max(regions, key=lambda region: region[2])

        # Map the box back onto the vehicle crop: undo the scale that was
        # actually applied, then add the ROI's vertical offset. Using the
        # nominal PLATE_UPSCALE_FACTOR here would be wrong whenever the width
        # clamp reduced the scale.
        crop_height_px = vehicle_crop_bgr.shape[0]
        roi_start_y_px = int(crop_height_px * (1.0 - self._settings.PLATE_ROI_FRACTION))

        xs = [point[0] / effective_scale for point in best_bbox]
        ys = [point[1] / effective_scale + roi_start_y_px for point in best_bbox]

        bbox_xywh = [
            int(min(xs)),
            int(min(ys)),
            int(max(xs) - min(xs)),
            int(max(ys) - min(ys)),
        ]
        return str(best_text), float(best_confidence), bbox_xywh

    def read_tracklet(self, best_shots: tuple[FrameSample, ...]) -> PlateRead:
        """Read the plate of one tracklet from its best-shot crops.

        The top PLATE_OCR_TOP_K crops are read and the highest-confidence
        result that survives normalisation wins. If none survives, the highest-confidence raw read is
        still reported so `plate_text_raw` preserves what OCR actually saw
        (schema.md section 3.6) — but `text_norm` stays None and `is_valid`
        stays False, so the backend's plate tier will not act on it.

        Args:
            best_shots: The top-K samples from best_shot.select_best_shots.

        Returns:
            A PlateRead. Never raises for an unreadable plate.
        """
        if not best_shots:
            return PlateRead.unread()

        best_valid: PlateRead | None = None
        best_raw_text: str | None = None
        best_raw_confidence = -1.0

        # Only the top PLATE_OCR_TOP_K crops are read. The embedder still
        # consumes all BEST_SHOT_TOP_K of them: embedding K crops is one batched
        # forward pass, whereas reading K crops is K sequential CPU OCR calls.
        # best_shots is already ordered best-first, so this takes the strongest.
        for sample in best_shots[: self._settings.PLATE_OCR_TOP_K]:
            read = self._read_one(sample.crop_bgr)
            if read is None:
                continue

            raw_text, confidence, bbox_xywh = read

            if confidence > best_raw_confidence:
                best_raw_confidence = confidence
                best_raw_text = raw_text

            if confidence < self._settings.OCR_MIN_CONFIDENCE:
                continue

            normalised, normalised_confidence = normalize_plate(raw_text, confidence)
            if normalised is None:
                continue

            if best_valid is None or normalised_confidence > (best_valid.confidence or -1.0):
                best_valid = PlateRead(
                    text_raw=raw_text,
                    text_norm=normalised,
                    confidence=normalised_confidence,
                    is_valid=True,
                    bbox_json=json.dumps(bbox_xywh),
                    plate_crop_bgr=self.extract_plate_roi(sample.crop_bgr),
                )

        if best_valid is not None:
            return best_valid

        if best_raw_text is None:
            return PlateRead.unread()

        # Read something, but it is not a plate. Keep the raw text for OCR error
        # analysis and leave the normalised fields empty.
        return PlateRead(
            text_raw=best_raw_text,
            text_norm=None,
            confidence=best_raw_confidence,
            is_valid=False,
            bbox_json=None,
            plate_crop_bgr=None,
        )
