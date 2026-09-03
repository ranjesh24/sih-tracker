"""Fetch model weights into ml-pipeline/models/ and report device availability.

Run once per machine, before going offline:

    python scripts/download_models.py

The demo must run with no network (requirement D-6, CLAUDE.md). Venue wifi
fails; every weight this pipeline needs has to be on disk beforehand. Weights
are gitignored and this script is what reproduces them (techspec.md section 3.3).

Two backbones are fetched:
  - YOLOv8s detector, into models/yolov8s.pt
  - OSNet x1.0 Re-ID, ImageNet-pretrained, via the vendored src/osnet.py

EasyOCR is deliberately not handled here. It downloads its detection and
recognition models into ~/.EasyOCR/model/ on first Reader construction rather
than to an arbitrary path, so it is warmed by instantiating a Reader; this
script does that last, and it is the slowest step.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import torch

# The pipeline package lives one level up from scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Settings, get_settings  # noqa: E402

YOLO_WEIGHTS_FILENAME = "yolov8s.pt"

# OSNet's classifier head is discarded; num_classes only shapes a layer that is
# never evaluated in eval mode.
OSNET_PLACEHOLDER_CLASS_COUNT = 1000


def report_device_availability() -> None:
    """Print what compute this host actually has.

    Printed first and unconditionally. Model download failures on a fresh
    machine are usually really device or driver problems, and knowing whether
    CUDA resolved before reading a stack trace saves the detour.
    """
    print("=" * 62)
    print("Device availability")
    print("=" * 62)
    print(f"  torch version        : {torch.__version__}")
    print(f"  CUDA available       : {torch.cuda.is_available()}")

    if torch.cuda.is_available():
        print(f"  CUDA version         : {torch.version.cuda}")
        print(f"  CUDA device count    : {torch.cuda.device_count()}")
        for index in range(torch.cuda.device_count()):
            print(f"    device {index}           : {torch.cuda.get_device_name(index)}")
    else:
        print("  CUDA version         : n/a")

    print(f"  MPS available        : {torch.backends.mps.is_available()}")

    if not torch.cuda.is_available():
        print()
        print("  No CUDA on this host. Set DEVICE=cpu (or DEVICE=mps on Apple")
        print("  silicon) in ml-pipeline/.env, or the worker will fail at startup.")
    print()


def download_yolo_weights(models_dir: Path) -> Path:
    """Fetch the YOLOv8s checkpoint into `models_dir`.

    Args:
        models_dir: Destination directory, created if absent.

    Returns:
        Path to the checkpoint inside `models_dir`.

    Raises:
        RuntimeError: If Ultralytics reports success but produces no file.
    """
    # Imported here, not at module scope: this pulls in the whole Ultralytics
    # stack, and the device report above should print even if that import is
    # what is broken.
    from ultralytics.utils.downloads import attempt_download_asset

    destination = models_dir / YOLO_WEIGHTS_FILENAME
    if destination.is_file():
        print(f"  YOLOv8s already present: {destination}")
        return destination

    print("  Fetching YOLOv8s ...")
    downloaded_path = Path(attempt_download_asset(YOLO_WEIGHTS_FILENAME))

    if not downloaded_path.is_file():
        raise RuntimeError(
            f"Ultralytics reported a download but {downloaded_path} does not exist"
        )

    if downloaded_path.resolve() != destination.resolve():
        shutil.move(str(downloaded_path), str(destination))

    print(f"  YOLOv8s ready: {destination}")
    return destination


def download_osnet_weights(models_dir: Path, settings: Settings) -> Path | None:
    """Fetch OSNet x1.0 ImageNet weights via the vendored architecture module.

    Uses src/osnet.py, the local copy of the deep-person-reid model definition.
    `torchreid` is deliberately NOT used: its setup.py pulls in the full
    training stack, which wants tensorboard, and the install is broken here.
    Only the inference-time definition is needed, so only that is vendored.

    The vendored module downloads to ~/.cache/torch/checkpoints on first use.
    That is NOT the same directory as torch.hub.get_dir(), which appends a
    `hub/` segment, so the path is resolved through the embedder's helper to
    keep both sides in agreement.

    Args:
        models_dir: Destination directory for a copy of the checkpoint.
        settings: Pipeline settings, for REID_MODEL_NAME.

    Returns:
        Path to the copied checkpoint, or None if the fetch did not produce one.
    """
    from src.embedder import osnet_checkpoint_path
    from src.osnet import osnet_x1_0

    print(f"  Fetching OSNet ({settings.REID_MODEL_NAME}) ...")

    # pretrained=True triggers the download if the checkpoint is not cached.
    # num_classes is a placeholder: the classifier head is discarded and only
    # the 512-D feature extractor is ever evaluated.
    osnet_x1_0(num_classes=OSNET_PLACEHOLDER_CLASS_COUNT, pretrained=True, loss="softmax")

    cached_path = osnet_checkpoint_path()
    if not cached_path.is_file():
        print(f"  OSNet weights were not written to {cached_path}.")
        return None

    destination = models_dir / cached_path.name
    if not destination.is_file():
        shutil.copy2(cached_path, destination)

    print(f"  OSNet ready: {destination}")
    return destination


def warm_easyocr_models() -> None:
    """Instantiate an EasyOCR Reader so its models land in the local cache."""
    try:
        import easyocr
    except ImportError:
        print("  easyocr is NOT installed, skipping. Run: pip install -r requirements.txt")
        return

    print("  Warming EasyOCR (downloads on first run, this is the slow step) ...")
    easyocr.Reader(["en"], gpu=False, verbose=False)
    print("  EasyOCR ready.")


def main() -> int:
    """Fetch every weight the pipeline needs.

    Returns:
        0 on success, 1 if a required download failed.
    """
    report_device_availability()

    settings = get_settings()
    models_dir = settings.MODELS_DIR_PATH
    models_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 62)
    print(f"Fetching weights into {models_dir.resolve()}")
    print("=" * 62)

    try:
        download_yolo_weights(models_dir)
    except (RuntimeError, OSError) as exc:
        print(f"  YOLOv8s download FAILED: {exc}", file=sys.stderr)
        return 1

    download_osnet_weights(models_dir, settings)
    warm_easyocr_models()

    print()
    print("Done. The pipeline can now run offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
