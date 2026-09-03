"""Table-driven plate normalisation tests, using real OCR failure strings.

The None cases carry as much weight as the success cases. An unreadable plate
must come back as None rather than as a partial or best-guess match: the
backend's plate tier is its highest-trust match method, so a manufactured plate
becomes a confident wrong identity that the spatio-temporal gate cannot catch.
"""

from __future__ import annotations

import pytest

from src.normalizer import (
    apply_positional_confusions,
    is_valid_plate,
    normalize_plate,
    strip_separators,
)

# (label, raw OCR text, expected normalised plate or None)
NORMALISATION_CASES: list[tuple[str, str, str | None]] = [
    # --- Already clean -------------------------------------------------------
    ("already valid", "BR01AB1234", "BR01AB1234"),
    ("single digit district", "BR1AB1234", "BR1AB1234"),
    ("no letter series", "BR011234", "BR011234"),
    ("three letter series", "MH12ABC1234", "MH12ABC1234"),
    # --- Separators and case -------------------------------------------------
    ("spaced as printed", "BR 01 AB 1234", "BR01AB1234"),
    ("hyphenated", "BR-01-AB-1234", "BR01AB1234"),
    ("dotted", "BR.01.AB.1234", "BR01AB1234"),
    ("lowercase", "br01ab1234", "BR01AB1234"),
    ("mixed separators and case", " Br-01 ab.1234 ", "BR01AB1234"),
    # --- Positional confusion corrections ------------------------------------
    # Digit in the state code: must become a letter.
    ("zero for O in state code", "8R01AB1234", "BR01AB1234"),
    ("five for S in state code", "5R01AB1234", "SR01AB1234"),
    # Letter in the district code: must become a digit.
    ("O for zero in district", "BRO1AB1234", "BR01AB1234"),
    ("I for one in district", "BROIAB1234", "BR01AB1234"),
    ("B for eight in district", "BRB1AB1234", "BR81AB1234"),
    ("Z for two in district", "BRZ1AB1234", "BR21AB1234"),
    # Letter in the serial: must become a digit.
    ("O for zero in serial", "BR01ABI234", "BR01AB1234"),
    ("S for five in serial", "BR01AB123S", "BR01AB1235"),
    ("multiple serial confusions", "BR01ABIZ34", "BR01AB1234"),
    # Both directions at once in one string.
    ("confusions in both directions", "8RO1AB123S", "BR01AB1235"),
    # --- The letter series is deliberately left alone ------------------------
    (
        "series letters are not digitised",
        "BR01OS1234",
        "BR01OS1234",
    ),
    # --- Real OCR failures that must return None -----------------------------
    ("smoke test output", "H~JHO WEF6035", None),
    ("pure noise", "|||", None),
    ("empty string", "", None),
    ("whitespace only", "   ", None),
    ("separators only", "---", None),
    ("too short", "BR011", None),
    ("too long", "BR01ABC12345", None),
    ("no digits at all", "ABCDEFG", None),
    ("all digits", "1234567890", None),
    ("vehicle badge text", "MARUTI SUZUKI", None),
    ("partial plate", "BR01AB", None),
    ("serial too short", "BR01AB12", None),
    ("state code unrecoverable", "4R01AB1234", None),
]


@pytest.mark.parametrize(
    ("label", "raw_text", "expected"),
    NORMALISATION_CASES,
    ids=[case[0] for case in NORMALISATION_CASES],
)
def test_normalisation_table(label: str, raw_text: str, expected: str | None) -> None:
    normalised, _ = normalize_plate(raw_text, ocr_confidence=0.9)

    assert normalised == expected


def test_unreadable_plate_returns_none_without_raising() -> None:
    """The expected case for most crops. It must be ordinary control flow."""
    normalised, confidence = normalize_plate("H~JHO WEF6035", ocr_confidence=0.142)

    assert normalised is None
    assert confidence == pytest.approx(0.142)


def test_none_input_is_handled_not_raised() -> None:
    normalised, confidence = normalize_plate(None, ocr_confidence=0.0)

    assert normalised is None
    assert confidence == 0.0


def test_confidence_passes_through_unchanged_on_success() -> None:
    """Normalisation adds no evidence about how well the characters were read."""
    _, confidence = normalize_plate("BR 01 AB 1234", ocr_confidence=0.83)

    assert confidence == pytest.approx(0.83)


def test_confidence_passes_through_unchanged_on_failure() -> None:
    _, confidence = normalize_plate("|||", ocr_confidence=0.31)

    assert confidence == pytest.approx(0.31)


def test_no_partial_match_fallback_is_invented() -> None:
    """A plate missing its serial must not be padded or salvaged."""
    normalised, _ = normalize_plate("BR01AB", ocr_confidence=0.95)

    assert normalised is None


def test_wrong_length_is_rejected_before_correction() -> None:
    """Correcting a wrong-length string could manufacture a plate from noise.

    'OOOOOOOOOOOO' is twelve characters. If positional correction ran before the
    length check, the prefix and suffix rules would rewrite it into something
    that could pass the pattern.
    """
    normalised, _ = normalize_plate("OOOOOOOOOOOO", ocr_confidence=0.9)

    assert normalised is None


def test_a_dropped_character_can_still_yield_a_valid_plate() -> None:
    """A known limitation of positional correction, pinned deliberately.

    'BR01AB123' is most likely 'BR01AB1234' with a digit dropped by OCR. At nine
    characters the trailing-serial window starts at index 5, so the series 'B'
    falls inside it and is corrected to '8', producing the valid but wrong
    'BR01A8123'.

    No positional scheme can distinguish this from a genuine nine-character
    plate, because both are structurally legal. The correction is kept because
    letters misread inside the serial ('BR01ABI234', 'BR01AB123S') are far more
    common than reads that drop exactly one character AND leave a confusable
    letter in the last four. This test exists so the trade-off is visible rather
    than discovered later from a wrong match in the backend.
    """
    normalised, _ = normalize_plate("BR01AB123", ocr_confidence=0.9)

    assert normalised == "BR01A8123"


def test_strip_separators_removes_ocr_junk() -> None:
    assert strip_separators("H~JHO WEF6035") == "HJHOWEF6035"


def test_strip_separators_uppercases() -> None:
    assert strip_separators("br-01-ab-1234") == "BR01AB1234"


def test_positional_correction_direction_depends_on_position() -> None:
    """The same character resolves differently at different positions.

    'O' in position 0 is a legitimate letter. 'O' in position 2 is a misread 0.
    """
    corrected = apply_positional_confusions("OROOAB1234")

    assert corrected[0] == "O", "position 0 is alphabetic, O must survive"
    assert corrected[2] == "0", "position 2 is numeric, O must become 0"


def test_valid_plate_pattern_accepts_documented_forms() -> None:
    assert is_valid_plate("BR01AB1234")
    assert is_valid_plate("MH12ABC1234")
    assert is_valid_plate("BR1A1234")
    assert is_valid_plate("BR011234")


def test_valid_plate_pattern_rejects_malformed() -> None:
    assert not is_valid_plate("B01AB1234")
    assert not is_valid_plate("BR01AB123")
    assert not is_valid_plate("BR01ABCD1234")
    assert not is_valid_plate("br01ab1234")


def test_normalizer_is_pure_and_repeatable() -> None:
    """Same input, same output, and normalising twice is a no-op."""
    first, _ = normalize_plate("BR 01 AB 1234", ocr_confidence=0.9)
    second, _ = normalize_plate("BR 01 AB 1234", ocr_confidence=0.9)

    assert first == second

    assert first is not None
    third, _ = normalize_plate(first, ocr_confidence=0.9)
    assert third == first
