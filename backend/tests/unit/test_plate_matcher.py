"""Unit tests for plate normalisation and OCR-tolerant matching (TASK-210)."""
from app.services.plate_matcher import (
    is_confusable_match,
    is_structurally_valid,
    match_score,
    normalise,
)


def test_normalise_uppercases_and_strips_separators() -> None:
    assert normalise("br 01-ab 1234") == "BR01AB1234"
    assert normalise("mh12.cd.5678") == "MH12CD5678"


def test_is_structurally_valid_accepts_valid_plates() -> None:
    assert is_structurally_valid("BR01AB1234") is True
    assert is_structurally_valid("MH12CD5678") is True
    assert is_structurally_valid("KA5M9999") is True  # 1-digit district, 1 letter


def test_is_structurally_valid_rejects_malformed() -> None:
    assert is_structurally_valid("BR01AB123") is False   # only 3 trailing digits
    assert is_structurally_valid("1234ABCD") is False     # wrong shape
    assert is_structurally_valid("") is False


def test_exact_match_scores_one() -> None:
    assert match_score("BR01AB1234", "BR01AB1234") == 1.0


def test_confusion_pair_b_vs_8_matches() -> None:
    # OCR read the 'B' in 'AB' as '8': BR01AB1234 vs BR01A81234. 8<->B confusion.
    assert match_score("BR01AB1234", "BR01A81234") == 1.0
    assert is_confusable_match("BR01AB1234", "BR01A81234") is True


def test_single_genuine_typo_is_within_edit_distance_one() -> None:
    # One non-confusion substitution (C -> D): accepted at edit distance 1,
    # but scores below a confusion-equivalent match.
    assert is_confusable_match("MH12CD5678", "MH12DD5678") is True
    assert match_score("MH12CD5678", "MH12DD5678") < 1.0


def test_genuine_non_match_scores_low_and_is_rejected() -> None:
    assert is_confusable_match("BR01AB1234", "MH12CD5678") is False
    assert match_score("BR01AB1234", "MH12CD5678") < 0.5


def test_multiple_confusions_still_match() -> None:
    # Two confusable swaps (0<->O and 5<->S) resolve to distance 0.
    assert match_score("MH20SO1234", "MH2O5O1234") == 1.0
