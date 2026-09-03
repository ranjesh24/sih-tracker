"""Plate normalisation and OCR-tolerant matching (techspec.md 5.6; TASK-210).

Pure functions, no I/O. The OCR confusion map folds characters a plate reader
routinely swaps into one class, so two reads of the same physical plate that
differ only by such a swap are treated as identical, and a genuine single-
character error is still within the accepted edit distance.
"""
import re

from rapidfuzz.distance import Levenshtein

# Edit distance (after folding the confusion map) at or below which two plates
# are considered the same physical plate. An algorithm invariant — one OCR
# error — not a tunable threshold.
MAX_PLATE_EDIT_DISTANCE: int = 1

# OCR confusion classes; the first member is the canonical representative.
_CONFUSION_CLASSES: tuple[tuple[str, ...], ...] = (
    ("0", "O"),
    ("1", "I", "L"),
    ("8", "B"),
    ("5", "S"),
    ("2", "Z"),
    ("6", "G"),
)
_CANONICAL: dict[str, str] = {
    char: members[0] for members in _CONFUSION_CLASSES for char in members
}

_PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$")
_SEPARATORS = re.compile(r"[^A-Z0-9]")

_EXACT_SCORE: float = 1.0
_NO_MATCH_SCORE: float = 0.0


def normalise(raw: str) -> str:
    """Uppercase and strip separators and whitespace from an OCR plate read."""
    return _SEPARATORS.sub("", raw.upper())


def is_structurally_valid(norm: str) -> bool:
    """Return True if the normalised plate matches the Indian plate structure."""
    return bool(_PLATE_REGEX.match(norm))


def _canonicalise(plate: str) -> str:
    """Fold each character to its OCR confusion-class representative."""
    return "".join(_CANONICAL.get(char, char) for char in plate)


def match_score(a: str, b: str) -> float:
    """Similarity of two normalised plates in [0, 1].

    Returns 1.0 for an exact or confusion-equivalent match; otherwise the
    confusion-folded normalised Levenshtein similarity.
    """
    if a == b:
        return _EXACT_SCORE
    canon_a, canon_b = _canonicalise(a), _canonicalise(b)
    distance = Levenshtein.distance(canon_a, canon_b)
    if distance == 0:
        return _EXACT_SCORE
    longest = max(len(canon_a), len(canon_b))
    if longest == 0:
        return _NO_MATCH_SCORE
    return max(_NO_MATCH_SCORE, 1.0 - distance / longest)


def is_confusable_match(a: str, b: str) -> bool:
    """Whether two normalised plates are the same plate within one OCR error.

    The confusion map is applied first, so confusable substitutions cost nothing
    and only genuine extra edits count toward ``MAX_PLATE_EDIT_DISTANCE``.
    """
    if a == b:
        return True
    distance = Levenshtein.distance(_canonicalise(a), _canonicalise(b))
    return distance <= MAX_PLATE_EDIT_DISTANCE
