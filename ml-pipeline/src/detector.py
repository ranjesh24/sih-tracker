"""Vehicle detection and ByteTrack association via Ultralytics YOLOv8s.

This module owns the one YOLO model instance in a worker process. It is
deliberately the only place that imports `ultralytics`, so the AGPL-3.0 surface
and the Ultralytics API surface are both confined to a single file: swapping in
an Apache-2.0 backbone (RT-DETR, YOLOX) means reimplementing this module and
nothing else (techspec.md section 2.1 licence flag).

Everything here is tier-1 work — detection and association only. No OCR and no
embedding is invoked from this module, directly or indirectly.

API note. Written against the installed Ultralytics 8.4.138, verified by
introspection rather than assumed (rules.md R2 corollary):
  - `YOLO.track(source, persist=..., **kwargs) -> list[Results]`
  - `Results.boxes` exposes `.xyxy`, `.conf`, `.cls` as float tensors
  - `Results.boxes.id` is a float tensor of track ids, or **None** when the
    tracker produced no association for this frame
  - `Results.names` maps COCO class id to class name
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

from src.config import Settings, get_settings
from src.types import Detection


class DetectorError(RuntimeError):
    """Raised when model weights are missing or the configured device is absent."""


def resolve_device(settings: Settings) -> str:
    """Confirm the configured compute device is actually available.

    Checked once at construction so an absent GPU fails when the worker starts
    rather than on frame 400 (rules.md R3, appflow.md section 6.4).

    Args:
        settings: Pipeline settings carrying DEVICE.

    Returns:
        The device string to hand to Ultralytics.

    Raises:
        DetectorError: If the configured device is not available on this host.
    """
    device = settings.DEVICE

    if device == "cuda" and not torch.cuda.is_available():
        raise DetectorError(
            "DEVICE=cuda but torch.cuda.is_available() is False. "
            "Set DEVICE=cpu or DEVICE=mps in ml-pipeline/.env."
        )
    if device == "mps" and not torch.backends.mps.is_available():
        raise DetectorError(
            "DEVICE=mps but torch.backends.mps.is_available() is False. "
            "Set DEVICE=cpu in ml-pipeline/.env."
        )
    return device


class VehicleDetector:
    """YOLOv8s restricted to vehicle classes, with optional ByteTrack association.

    The class *name* is carried through from the model's own label map rather
    than a hardcoded id-to-name table. The backend gates matches on
    `vehicle_class` (schema.md section 3.6), so the label must survive into the
    Sighting intact; deriving it from the model is what keeps it correct if the
    configured class ids ever change.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Load the detector and validate its weights and device.

        Args:
            settings: Pipeline settings; the process singleton when omitted.

        Raises:
            DetectorError: If the weights file is missing or the device is absent.
        """
        self._settings = settings if settings is not None else get_settings()

        weights_path: Path = self._settings.YOLO_MODEL_PATH
        if not weights_path.is_file():
            raise DetectorError(
                f"YOLO weights not found at {weights_path}. "
                "Run: python scripts/download_models.py"
            )

        self._device = resolve_device(self._settings)
        self._model = YOLO(str(weights_path))
        self._class_ids = list(self._settings.TARGET_CLASS_IDS)

    @property
    def class_names(self) -> dict[int, str]:
        """The model's COCO class id to name map."""
        return self._model.names

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Detect vehicles in one frame, without tracking.

        Args:
            frame_bgr: A decoded BGR frame.

        Returns:
            One Detection per surviving box, vehicle classes only.
        """
        results = self._model.predict(
            frame_bgr,
            conf=self._settings.DETECTION_CONF_MIN,
            iou=self._settings.DETECTION_IOU_MAX,
            classes=self._class_ids,
            device=self._device,
            verbose=False,
        )
        return [detection for _, detection in self._to_detections(results[0], with_ids=False)]

    def track(self, frame_bgr: np.ndarray) -> list[tuple[int, Detection]]:
        """Detect and associate vehicles in one frame using ByteTrack.

        `persist=True` keeps the tracker's state across calls, which is what
        makes track ids stable from frame to frame within one video.

        Args:
            frame_bgr: A decoded BGR frame.

        Returns:
            (track_id, Detection) pairs. Boxes the tracker failed to associate
            carry no id and are omitted — an unassociated box cannot be
            attributed to a tracklet, and inventing an id for it would corrupt
            one.
        """
        results = self._model.track(
            frame_bgr,
            persist=True,
            conf=self._settings.DETECTION_CONF_MIN,
            iou=self._settings.DETECTION_IOU_MAX,
            classes=self._class_ids,
            device=self._device,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        return self._to_detections(results[0], with_ids=True)

    def _to_detections(self, result: object, with_ids: bool) -> list[tuple[int, Detection]]:
        """Convert one Ultralytics Results object into Detection instances.

        Args:
            result: A single `ultralytics.engine.results.Results`.
            with_ids: Whether to require and attach ByteTrack ids.

        Returns:
            (track_id, Detection) pairs; track_id is -1 when `with_ids` is False.
        """
        boxes = result.boxes  # type: ignore[attr-defined]
        if boxes is None or len(boxes) == 0:
            return []

        # `.id` is None whenever the tracker associated nothing this frame.
        track_ids = boxes.id
        if with_ids and track_ids is None:
            return []

        names: dict[int, str] = result.names  # type: ignore[attr-defined]
        pairs: list[tuple[int, Detection]] = []

        for row in range(len(boxes)):
            x1, y1, x2, y2 = (float(value) for value in boxes.xyxy[row].tolist())
            class_id = int(boxes.cls[row].item())

            detection = Detection(
                bbox_x_px=int(x1),
                bbox_y_px=int(y1),
                bbox_w_px=int(x2 - x1),
                bbox_h_px=int(y2 - y1),
                det_conf=float(boxes.conf[row].item()),
                class_id=class_id,
                class_name=names[class_id],
            )

            # A degenerate box would violate the CHECK (bbox_w > 0) constraint on
            # the sightings table, so drop it here rather than at ingest.
            if detection.bbox_w_px <= 0 or detection.bbox_h_px <= 0:
                continue

            track_id = int(track_ids[row].item()) if with_ids else -1
            pairs.append((track_id, detection))

        return pairs
