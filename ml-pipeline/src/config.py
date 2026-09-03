"""Central configuration for the ML pipeline.

Every tunable value in the pipeline lives here and is loaded from the
environment via pydantic-settings (rules.md section 3, "Configuration").

No numeric literal appears in logic anywhere else in this codebase. Every
threshold below will be tuned against real footage during Phase 3, and a value
hardcoded in a function body is one that cannot be changed without a code edit
and a restart at 11 p.m. on Friday.

Validation happens at import, not at first use: a missing weight file or an
unavailable device must fail when the worker starts, not on frame 400
(appflow.md section 6.4, rules.md R3).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DeviceName = Literal["cuda", "cpu", "mps"]


class Settings(BaseSettings):
    """Pipeline settings, read from ml-pipeline/.env and the process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- Backend connection --------------------------------------------------
    BACKEND_BASE_URL: str = "http://localhost:8000"
    INGEST_API_KEY: str = ""

    # --- Runtime -------------------------------------------------------------
    DEVICE: DeviceName = "cuda"
    MODELS_DIR_PATH: Path = Path("./models")

    # --- Video decode --------------------------------------------------------
    # Nominal playback rate, used to derive frame timestamps from the frame
    # index. See video_source.py for why this is not wall-clock time.
    PLAYBACK_FPS: float = Field(default=15.0, gt=0.0)

    # Process every Nth decoded frame. 1 processes every frame. This controls
    # which frames are *processed*, never how a processed frame is *timed*.
    FRAME_STRIDE: int = Field(default=2, ge=1)

    # --- Detection -----------------------------------------------------------
    YOLO_MODEL_PATH: Path = Path("./models/yolov8s.pt")
    DETECTION_CONF_MIN: float = Field(default=0.35, ge=0.0, le=1.0)
    DETECTION_IOU_MAX: float = Field(default=0.50, ge=0.0, le=1.0)

    # COCO class ids kept by the detector: 2 car, 3 motorcycle, 5 bus, 7 truck.
    # Stored as CSV rather than list[int] because pydantic-settings JSON-decodes
    # complex-typed env values, which would require "[2,3,5,7]" in the .env file.
    TARGET_CLASS_IDS_CSV: str = "2,3,5,7"

    # --- Tracking ------------------------------------------------------------
    BYTETRACK_TRACK_CONF_MIN: float = Field(default=0.50, ge=0.0, le=1.0)
    BYTETRACK_MATCH_IOU_MIN: float = Field(default=0.80, ge=0.0, le=1.0)
    BYTETRACK_BUFFER_FRAMES: int = Field(default=30, ge=1)

    # Frames a track id may go unseen before its tracklet is finalised. Counted
    # in processed frames, so it is already expressed in post-stride units.
    TRACK_LOST_FRAMES: int = Field(default=30, ge=1)

    # Finalised tracklets shorter than this are discarded as detector noise.
    TRACKLET_MIN_FRAMES: int = Field(default=8, ge=1)

    # --- Best-shot selection -------------------------------------------------
    BEST_SHOT_TOP_K: int = Field(default=5, ge=1)
    BEST_SHOT_MIN_AREA_PX: int = Field(default=2500, ge=0)

    # --- Re-ID ---------------------------------------------------------------
    REID_MODEL_NAME: str = "osnet_x1_0"

    # 256x256 per the TASK-000 amendment. 256x128 is a person aspect ratio;
    # vehicles are wide, and squashing them to 2:1 discards shape information
    # the embedding depends on. Exposed as the pair REID_INPUT_SIZE_PX below.
    REID_INPUT_HEIGHT_PX: int = Field(default=256, ge=1)
    REID_INPUT_WIDTH_PX: int = Field(default=256, ge=1)

    REID_BATCH_SIZE: int = Field(default=16, ge=1)
    REID_EMBEDDING_DIM: int = Field(default=512, ge=1)

    # --- Plate OCR -----------------------------------------------------------
    OCR_MIN_CONFIDENCE: float = Field(default=0.40, ge=0.0, le=1.0)

    # Fraction of the vehicle box, measured from the bottom, searched for a
    # plate. Indian plates sit low on the vehicle, and cropping to the lower
    # band keeps OCR away from badge text, bumper stickers and shop signage
    # behind the vehicle, which is where most junk reads come from.
    PLATE_ROI_FRACTION: float = Field(default=0.40, gt=0.0, le=1.0)

    # Plate crops arrive far below the resolution EasyOCR's recogniser expects,
    # so the ROI is upscaled before the read.
    PLATE_UPSCALE_FACTOR: int = Field(default=4, ge=1)

    # Ceiling on the upscaled ROI width. A frame-filling vehicle upscaled by a
    # pure multiplier reaches ~2560 px wide, and EasyOCR's cost grows with pixel
    # count, which is where 7.4 s per call came from. This caps the worst case
    # without touching small distant plates: they never reach the ceiling, so
    # they still upscale by the full factor.
    PLATE_ROI_MAX_WIDTH_PX: int = Field(default=640, ge=1)

    # How many of the best shots get an OCR pass. Distinct from BEST_SHOT_TOP_K,
    # which the embedder still uses in full: embedding K crops is one batched
    # forward pass, while reading K crops is K sequential CPU OCR calls, so the
    # two have very different marginal costs.
    PLATE_OCR_TOP_K: int = Field(default=3, ge=1)

    # --- Ingest client -------------------------------------------------------
    INGEST_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0.0)
    INGEST_MAX_RETRIES: int = Field(default=3, ge=0)
    # First retry waits this long; each subsequent retry doubles it.
    INGEST_BACKOFF_BASE_SECONDS: float = Field(default=0.5, gt=0.0)

    # --- Visualisation -------------------------------------------------------
    VISUALIZE_OUTPUT_FPS: float = Field(default=15.0, gt=0.0)

    # --- Storage -------------------------------------------------------------
    CROP_STORAGE_PATH: Path = Path("./data/crops")

    @field_validator("TARGET_CLASS_IDS_CSV")
    @classmethod
    def _validate_class_ids_csv(cls, raw: str) -> str:
        """Reject a malformed class list at startup rather than mid-run."""
        if not raw.strip():
            raise ValueError("TARGET_CLASS_IDS_CSV must list at least one COCO class id")
        for part in raw.split(","):
            if not part.strip().isdigit():
                raise ValueError(
                    f"TARGET_CLASS_IDS_CSV must be comma-separated integers, got {raw!r}"
                )
        return raw

    @property
    def TARGET_CLASS_IDS(self) -> tuple[int, ...]:
        """COCO class ids the detector keeps, parsed from the CSV field."""
        return tuple(int(part.strip()) for part in self.TARGET_CLASS_IDS_CSV.split(","))

    @property
    def REID_INPUT_SIZE_PX(self) -> tuple[int, int]:
        """Re-ID input size as (height_px, width_px)."""
        return (self.REID_INPUT_HEIGHT_PX, self.REID_INPUT_WIDTH_PX)

    @property
    def SECONDS_PER_FRAME(self) -> float:
        """Wall-clock seconds represented by one frame at PLAYBACK_FPS."""
        return 1.0 / self.PLAYBACK_FPS


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Returns:
        The Settings instance, parsed once and cached.

    Raises:
        pydantic.ValidationError: If any environment value is absent or invalid.
    """
    return Settings()
