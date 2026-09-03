"""Embedding shape, norm, and the guarantees that keep them meaningful.

These load the real backbone. That is deliberate despite rules.md section 6
discouraging model loads in unit tests: the single most valuable property to
assert is that the weights are genuinely pretrained, and a mocked embedder
cannot test that. The load is fast because the checkpoint is cached locally.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.config import Settings
from src.embedder import EmbedderError, VehicleEmbedder, osnet_checkpoint_path
from src.osnet import osnet_x1_0

EXPECTED_EMBEDDING_DIM = 512


@pytest.fixture(scope="module")
def embedder() -> VehicleEmbedder:
    """One embedder for the module: construction loads a network."""
    return VehicleEmbedder(Settings(DEVICE="mps", CROP_STORAGE_PATH=Path("/tmp/marg")))


def make_crop(seed: int, size_px: int = 128) -> np.ndarray:
    rng = np.random.default_rng(seed=seed)
    return rng.integers(0, 256, size=(size_px, size_px, 3), dtype=np.uint8)


def test_embedding_has_exactly_512_dimensions(embedder: VehicleEmbedder) -> None:
    vector = embedder.embed_crops([make_crop(1)])

    assert len(vector) == EXPECTED_EMBEDDING_DIM


def test_embedding_is_unit_norm(embedder: VehicleEmbedder) -> None:
    vector = embedder.embed_crops([make_crop(2)])

    assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-5)


def test_embedding_is_a_plain_float_list(embedder: VehicleEmbedder) -> None:
    """It is JSON-serialised onto the ingest wire, so no numpy types."""
    vector = embedder.embed_crops([make_crop(3)])

    assert isinstance(vector, list)
    assert all(isinstance(value, float) for value in vector)


def test_batched_embedding_is_unit_norm(embedder: VehicleEmbedder) -> None:
    """The mean of K vectors is normalised once, after averaging."""
    crops = [make_crop(seed) for seed in range(5)]

    vector = embedder.embed_crops(crops)

    assert len(vector) == EXPECTED_EMBEDDING_DIM
    assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-5)


def test_normalisation_happens_after_averaging_not_before(
    embedder: VehicleEmbedder,
) -> None:
    """Distinguish the two orderings, which give genuinely different answers.

    Averaging pre-normalised vectors is not the same as normalising the mean of
    raw vectors. If the two crops differ in magnitude, the orderings disagree,
    so the batched result must not equal the mean of the individually
    normalised results.
    """
    crop_one = make_crop(11)
    crop_two = make_crop(22, size_px=200)

    batched = np.array(embedder.embed_crops([crop_one, crop_two]))

    individually_normalised = np.mean(
        [
            np.array(embedder.embed_crops([crop_one])),
            np.array(embedder.embed_crops([crop_two])),
        ],
        axis=0,
    )
    renormalised = individually_normalised / np.linalg.norm(individually_normalised)

    assert not np.allclose(batched, renormalised, atol=1e-6)


def test_embedding_is_deterministic(embedder: VehicleEmbedder) -> None:
    crop = make_crop(7)

    first = embedder.embed_crops([crop])
    second = embedder.embed_crops([crop])

    assert np.allclose(first, second, atol=1e-6)


def test_different_crops_give_different_embeddings(embedder: VehicleEmbedder) -> None:
    """Guards against a degenerate backbone returning a constant vector."""
    first = np.array(embedder.embed_crops([make_crop(100)]))
    second = np.array(embedder.embed_crops([make_crop(200)]))

    assert not np.allclose(first, second, atol=1e-4)


def test_empty_crop_list_raises(embedder: VehicleEmbedder) -> None:
    with pytest.raises(EmbedderError, match="empty crop list"):
        embedder.embed_crops([])


def test_empty_tracklet_raises(embedder: VehicleEmbedder) -> None:
    with pytest.raises(EmbedderError, match="no best shots"):
        embedder.embed_tracklet(())


def test_checkpoint_is_present_where_the_vendored_module_writes_it() -> None:
    """torch.hub.get_dir() and osnet.py disagree; this pins the right one."""
    assert osnet_checkpoint_path().is_file(), (
        f"expected the OSNet checkpoint at {osnet_checkpoint_path()}"
    )


def test_randomly_initialised_weights_are_rejected() -> None:
    """The check that stops the worst failure mode from being silent.

    Random init yields perfectly well-formed 512-D unit-norm vectors, so every
    other assertion in this file would still pass while similarity scores were
    noise. Verification must reject it.
    """
    random_model = osnet_x1_0(num_classes=1000, pretrained=False, loss="softmax")

    with pytest.raises(EmbedderError, match="randomly initialised|do not match"):
        VehicleEmbedder._verify_weights_are_pretrained(random_model)


def test_pretrained_weights_are_accepted() -> None:
    """The same check must not reject genuine weights."""
    pretrained_model = osnet_x1_0(num_classes=1000, pretrained=True, loss="softmax")

    VehicleEmbedder._verify_weights_are_pretrained(pretrained_model)
