"""OSNet appearance embeddings for a finalised tracklet. Tier-2 work only.

Vendored backbone
-----------------
The architecture is imported from `src/osnet.py`, a local copy of the OSNet
definition from deep-person-reid (MIT). `torchreid` itself is NOT installed and
must not be imported anywhere: its setup.py pulls in the full training stack,
which wants tensorboard, and the install is broken in this environment. Only the
inference-time model definition is needed, so only that is vendored.

Weights must be real
--------------------
The model is built with `pretrained=True` against the ImageNet checkpoint cached
at ~/.cache/torch/checkpoints/osnet_x1_0_imagenet.pth, and the load is verified
explicitly rather than trusted.

This matters more than it looks. Randomly initialised OSNet still emits
well-formed 512-D unit-norm vectors. Every shape assertion passes, every test
passes, the pipeline runs end to end — and the cosine similarities are noise, so
cross-camera matching silently degrades to chance. A failure that leaves all the
observable invariants intact is the worst kind, so a failed weight load raises
here instead of falling back to random init.

Normalise after averaging, never before
---------------------------------------
The K best shots are embedded in ONE batched forward pass, the outputs are
averaged, and the mean is L2-normalised once (schema.md section 4: embeddings
are normalised exactly once).

Order matters. Normalising each vector before averaging discards the magnitude
information that weights confident views more heavily, and the resulting mean is
not unit length anyway, so it would need renormalising regardless. Averaging
first and normalising once is both cheaper and more faithful.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import Tensor

from src.config import Settings, get_settings
from src.osnet import osnet_x1_0
from src.types import FrameSample

# ImageNet channel statistics. These are fixed by the pretrained backbone rather
# than tunable: changing them silently invalidates the weights, so they are named
# constants here rather than configuration.
IMAGENET_MEAN_RGB = (0.485, 0.456, 0.406)
IMAGENET_STD_RGB = (0.229, 0.224, 0.225)

# OSNet's classifier head is discarded; num_classes only shapes a layer that is
# never evaluated in eval mode.
OSNET_PLACEHOLDER_CLASS_COUNT = 1000

# The cached ImageNet checkpoint, and the tensor compared against it to prove
# the weights genuinely loaded.
OSNET_CHECKPOINT_FILENAME = "osnet_x1_0_imagenet.pth"
OSNET_REFERENCE_TENSOR_KEY = "conv1.conv.weight"

UINT8_MAX = 255.0


class EmbedderError(RuntimeError):
    """Raised when the backbone cannot be built with genuine pretrained weights."""


def osnet_checkpoint_path() -> Path:
    """Resolve where the vendored osnet module caches its ImageNet checkpoint.

    This deliberately mirrors `_get_torch_home()` inside src/osnet.py rather
    than calling `torch.hub.get_dir()`. They disagree: torch.hub appends a
    `hub/` segment, giving ~/.cache/torch/hub/checkpoints, while osnet.py writes
    to ~/.cache/torch/checkpoints. Verifying against the wrong directory would
    report a missing checkpoint for weights that had in fact loaded correctly.

    Returns:
        Path to osnet_x1_0_imagenet.pth, whether or not it exists.
    """
    torch_home = os.path.expanduser(
        os.getenv(
            "TORCH_HOME",
            os.path.join(os.getenv("XDG_CACHE_HOME", "~/.cache"), "torch"),
        )
    )
    return Path(torch_home) / "checkpoints" / OSNET_CHECKPOINT_FILENAME


def _resolve_torch_device(settings: Settings) -> torch.device:
    """Pick a device, preferring the configured one and degrading cleanly.

    Args:
        settings: Pipeline settings carrying DEVICE.

    Returns:
        A torch.device that is actually usable on this host.
    """
    requested = settings.DEVICE

    if requested == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    if requested == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    if requested == "cpu":
        return torch.device("cpu")

    # Configured device is unavailable. Prefer MPS on this machine, else CPU.
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class VehicleEmbedder:
    """Produces one 512-D L2-normalised appearance vector per tracklet."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Build OSNet once, with verified pretrained weights.

        Args:
            settings: Pipeline settings; the process singleton when omitted.

        Raises:
            EmbedderError: If the pretrained weights could not be loaded.
        """
        self._settings = settings if settings is not None else get_settings()
        self._device = _resolve_torch_device(self._settings)

        self._ensure_cached_weights()

        model = osnet_x1_0(
            num_classes=OSNET_PLACEHOLDER_CLASS_COUNT,
            pretrained=True,
            loss="softmax",
        )
        self._verify_weights_are_pretrained(model)

        self._model = model.eval().to(self._device)

        mean = torch.tensor(IMAGENET_MEAN_RGB, dtype=torch.float32).view(1, 3, 1, 1)
        std = torch.tensor(IMAGENET_STD_RGB, dtype=torch.float32).view(1, 3, 1, 1)
        self._mean_rgb = mean.to(self._device)
        self._std_rgb = std.to(self._device)

    @staticmethod
    def _ensure_cached_weights() -> None:
        """Copy local model weights to the torch cache if not already there."""
        cache_path = osnet_checkpoint_path()
        if cache_path.is_file():
            return
        local_weights = Path(__file__).resolve().parent.parent / "models" / OSNET_CHECKPOINT_FILENAME
        if local_weights.is_file():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_weights, cache_path)

    @staticmethod
    def _verify_weights_are_pretrained(model: torch.nn.Module) -> None:
        """Confirm the ImageNet checkpoint actually loaded, by direct comparison.

        `init_pretrained_weights` in the vendored module warns rather than
        raises when no layer names match, which would leave a randomly
        initialised network behind. Random init produces perfectly well-formed
        unit-norm 512-D vectors, so nothing downstream would notice.

        A statistical test on the weights is not good enough here: random init
        and trained weights both produce a healthy spread, so a threshold on
        standard deviation passes for both. The only reliable check is to read
        the checkpoint back off disk and compare a tensor against it.

        Raises:
            EmbedderError: If the checkpoint is missing, unreadable, or did not
                make it into the model.
        """
        checkpoint_path = osnet_checkpoint_path()
        if not checkpoint_path.is_file():
            raise EmbedderError(
                f"OSNet ImageNet checkpoint not found at {checkpoint_path}. "
                "Refusing to run with untrained weights, which would emit "
                "valid-looking 512-D vectors with meaningless similarity scores. "
                "Run: python scripts/download_models.py"
            )

        try:
            checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        except (OSError, RuntimeError, EOFError) as exc:
            raise EmbedderError(
                f"OSNet checkpoint at {checkpoint_path} could not be read: {exc}"
            ) from exc

        state_dict = checkpoint.get("state_dict", checkpoint)
        reference = state_dict.get(OSNET_REFERENCE_TENSOR_KEY)
        if reference is None:
            raise EmbedderError(
                f"OSNet checkpoint is missing {OSNET_REFERENCE_TENSOR_KEY}; it is "
                f"not the expected ImageNet checkpoint. Path: {checkpoint_path}"
            )

        loaded = model.conv1.conv.weight.detach().cpu()
        if not torch.allclose(loaded, reference.cpu()):
            raise EmbedderError(
                "OSNet was built but its weights do not match the checkpoint at "
                f"{checkpoint_path}, so the model is effectively randomly "
                "initialised. Refusing to run: the embeddings would be "
                "well-formed but their similarity scores meaningless."
            )

    @property
    def device(self) -> torch.device:
        """The device the backbone is resident on."""
        return self._device

    def _to_batch_tensor(self, crops_bgr: list[np.ndarray]) -> Tensor:
        """Resize, convert and normalise crops into one NCHW batch.

        Args:
            crops_bgr: Vehicle crops in BGR uint8.

        Returns:
            A float32 tensor of shape (N, 3, H, W) on the model's device.
        """
        height_px, width_px = self._settings.REID_INPUT_SIZE_PX

        resized: list[np.ndarray] = []
        for crop_bgr in crops_bgr:
            # INTER_AREA for downscaling, which is the usual direction here and
            # avoids the aliasing INTER_LINEAR introduces on large reductions.
            scaled = cv2.resize(
                crop_bgr, (width_px, height_px), interpolation=cv2.INTER_AREA
            )
            resized.append(cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB))

        stacked = np.stack(resized).astype(np.float32) / UINT8_MAX
        # NHWC to NCHW.
        batch = torch.from_numpy(stacked).permute(0, 3, 1, 2).to(self._device)

        return (batch - self._mean_rgb) / self._std_rgb

    def embed_crops(self, crops_bgr: list[np.ndarray]) -> list[float]:
        """Embed crops in one forward pass and return the normalised mean.

        Args:
            crops_bgr: One or more vehicle crops in BGR.

        Returns:
            A 512-element list of floats with unit L2 norm.

        Raises:
            EmbedderError: If no crops were supplied, or the backbone returned
                an unexpected dimensionality.
        """
        if not crops_bgr:
            raise EmbedderError("cannot embed an empty crop list")

        batch = self._to_batch_tensor(crops_bgr)

        with torch.no_grad():
            # One batched pass, not a loop: K forward passes of batch size 1
            # cost far more than one pass of batch size K.
            features = self._model(batch)

        expected_dim = self._settings.REID_EMBEDDING_DIM
        if features.ndim != 2 or features.shape[1] != expected_dim:
            raise EmbedderError(
                f"OSNet returned shape {tuple(features.shape)}, expected "
                f"(N, {expected_dim})"
            )

        # Average first, then normalise exactly once.
        mean_vector = features.mean(dim=0)

        norm = torch.linalg.vector_norm(mean_vector)
        if not torch.isfinite(norm) or float(norm) == 0.0:
            raise EmbedderError(f"mean embedding has degenerate norm {float(norm)}")

        normalised = (mean_vector / norm).cpu().numpy().astype(np.float32)

        # Asserted in the code, not only in tests: a malformed embedding reaching
        # the backend corrupts the FAISS index rather than failing loudly.
        if normalised.shape != (expected_dim,):
            raise EmbedderError(
                f"embedding has shape {normalised.shape}, expected ({expected_dim},)"
            )

        final_norm = float(np.linalg.norm(normalised))
        if not np.isclose(final_norm, 1.0, atol=1e-5):
            raise EmbedderError(f"embedding is not unit norm: {final_norm}")

        return [float(value) for value in normalised]

    def embed_tracklet(self, best_shots: tuple[FrameSample, ...]) -> list[float]:
        """Embed a tracklet from its best-shot crops.

        Args:
            best_shots: The top-K samples from best_shot.select_best_shots.

        Returns:
            A 512-element unit-norm embedding.

        Raises:
            EmbedderError: If the tracklet carries no samples.
        """
        if not best_shots:
            raise EmbedderError("cannot embed a tracklet with no best shots")

        return self.embed_crops([sample.crop_bgr for sample in best_shots])
