"""Vector index and embedding byte-layout (schema.md 4; techspec.md 3.2).

Normalisation happens on write, exactly once, in :func:`encode_embedding`. Every
vector stored in the database and in FAISS is therefore unit-length, so an
``IndexFlatIP`` inner product equals cosine similarity with no further work
(CLAUDE.md; schema.md section 4).

``faiss`` is imported nowhere else in the codebase (techspec.md 3.2): the index
lives behind this class. FAISS ids must be int64, but ``sightings.id`` is a UUID
string, so this class keeps a bidirectional int<->uuid map internally rather than
changing the schema.
"""
import faiss
import numpy as np
from sqlmodel import Session

from app.repositories import sighting_repo

EMBEDDING_DIM_DEFAULT: int = 512


def encode_embedding(vec: np.ndarray) -> bytes:
    """L2-normalise, cast to float32, return contiguous bytes.

    Args:
        vec: A real-valued embedding of any shape; it is ravelled to 1-D.

    Returns:
        The unit-length float32 vector as C-contiguous bytes, ready for the
        ``embedding`` BLOB column.
    """
    v = np.asarray(vec, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(v))
    if norm > 0:
        v = v / norm
    return np.ascontiguousarray(v).tobytes()


def decode_embedding(blob: bytes, dim: int = EMBEDDING_DIM_DEFAULT) -> np.ndarray:
    """Decode a stored embedding BLOB back to a float32 vector.

    Args:
        blob: The bytes from the ``embedding`` column.
        dim: The expected dimensionality; a mismatch is an error, not a reshape.

    Returns:
        A 1-D float32 ``numpy`` array of length ``dim``.

    Raises:
        ValueError: If the decoded length does not equal ``dim``.
    """
    v = np.frombuffer(blob, dtype=np.float32)
    if v.size != dim:
        raise ValueError(f"Embedding dimension mismatch: got {v.size}, expected {dim}")
    return v


class VectorIndex:
    """In-memory FAISS index over sighting embeddings (techspec.md 3.2).

    ``IndexIDMap2`` wrapping ``IndexFlatIP`` (exact inner product). Vectors are
    expected to be unit-length already (see :func:`encode_embedding`); this class
    does not re-normalise, because normalising twice produces subtly wrong scores.
    """

    def __init__(self, dim: int = EMBEDDING_DIM_DEFAULT) -> None:
        self._dim = dim
        self._index: faiss.IndexIDMap2 = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))
        self._uuid_to_int: dict[str, int] = {}
        self._int_to_uuid: dict[int, str] = {}
        self._vectors: dict[str, np.ndarray] = {}
        self._next_int: int = 0

    @property
    def dim(self) -> int:
        """The dimensionality this index accepts."""
        return self._dim

    def __len__(self) -> int:
        return int(self._index.ntotal)

    def _prepare(self, vector: np.ndarray) -> np.ndarray:
        v = np.asarray(vector, dtype=np.float32).ravel()
        if v.size != self._dim:
            raise ValueError(
                f"Embedding dimension mismatch: got {v.size}, expected {self._dim}"
            )
        return v

    def _intern(self, sighting_id: str) -> int:
        existing = self._uuid_to_int.get(sighting_id)
        if existing is not None:
            return existing
        int_id = self._next_int
        self._next_int += 1
        self._uuid_to_int[sighting_id] = int_id
        self._int_to_uuid[int_id] = sighting_id
        return int_id

    def add(self, sighting_id: str, vector: np.ndarray) -> None:
        """Add a unit-length vector under its ``sightings.id``.

        Raises:
            ValueError: if ``vector`` does not have this index's dimensionality.
        """
        v = self._prepare(vector)
        int_id = self._intern(sighting_id)
        self._index.add_with_ids(
            v.reshape(1, -1), np.array([int_id], dtype=np.int64)
        )
        self._vectors[sighting_id] = v

    def search(self, vector: np.ndarray, k: int) -> list[tuple[str, float]]:
        """Return up to ``k`` nearest sightings as ``(sighting_id, cosine)`` pairs."""
        v = self._prepare(vector)
        if len(self) == 0 or k <= 0:
            return []
        top_k = min(k, len(self))
        distances, ids = self._index.search(v.reshape(1, -1), top_k)
        results: list[tuple[str, float]] = []
        for score, int_id in zip(distances[0], ids[0]):
            if int_id == -1:
                continue
            clamped = max(-1.0, min(1.0, float(score)))
            results.append((self._int_to_uuid[int(int_id)], clamped))
        return results

    def search_subset(
        self, vector: np.ndarray, candidate_sighting_ids: list[str]
    ) -> dict[str, float]:
        """Cosine of ``vector`` against a known candidate set only.

        This is what the amended resolver uses: score against the spatio-temporal
        feasible set rather than the whole index. Candidates absent from the index
        are skipped.
        """
        v = self._prepare(vector)
        scores: dict[str, float] = {}
        for sighting_id in candidate_sighting_ids:
            stored = self._vectors.get(sighting_id)
            if stored is None:
                continue
            dot = float(np.dot(v, stored))
            scores[sighting_id] = max(-1.0, min(1.0, dot))
        return scores

    def _reset(self) -> None:
        self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(self._dim))
        self._uuid_to_int.clear()
        self._int_to_uuid.clear()
        self._vectors.clear()
        self._next_int = 0

    def rebuild_from_db(self, session: Session) -> int:
        """Reload the index from persisted embeddings (NFR-R2 startup rebuild).

        Returns the number of vectors loaded.
        """
        self._reset()
        count = 0
        for sighting in sighting_repo.get_since(session, None):
            if sighting.embedding is None:
                continue
            vector = decode_embedding(sighting.embedding, self._dim)
            self.add(sighting.id, vector)
            count += 1
        return count
