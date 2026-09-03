"""Plate text normalisation and validation. Pure functions, no I/O.

Returning None is the normal outcome, not a failure
---------------------------------------------------
Most crops do not yield a readable plate. The vehicle is angled away, the plate
is occluded, the crop is 40 pixels wide, or OCR simply returns noise. That is
the premise of the project rather than an error condition: the whole reason the
system fuses appearance embeddings and a spatio-temporal gate is that plate
reads are unreliable, and a vehicle whose plate is never read still has to be
tracked across cameras.

So an unreadable plate returns `(None, confidence)`. It does not raise, does not
log at warning level, and never falls back to a partial or best-guess match. A
partial plate that reaches the backend's plate tier is worse than no plate at
all: `PLATE_EXACT` and `PLATE_FUZZY` are the highest-trust match methods, so a
wrong plate produces a confident wrong identity, which is the one failure mode
the gate cannot catch.

Positional confusion correction
-------------------------------
OCR confuses characters that look alike. Which way to correct a confusion
depends on where the character sits, because the Indian plate format fixes
whether each position is alphabetic or numeric:

    BR 01 AB 1234
    ^^ ^^ ^^ ^^^^
    |  |  |  +---- 4 digits
    |  |  +------- 0-3 letter series
    |  +---------- 1-2 digit district code
    +------------- 2 letter state code

An `O` in position 0 is a letter and correct. The same `O` in position 2 is a
misread `0`. One confusion map, applied in opposite directions depending on
position (schema.md section 3.6 keeps `plate_text_raw` alongside the normalised
form precisely so this correction can be audited afterwards).
"""

from __future__ import annotations

import re

# Structural constants of the Indian plate format, not tunable thresholds, so
# they live here rather than in config.py. The pattern is quoted from
# schema.md section 3.6, which defines plate_is_valid.
PLATE_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$")

# Positions 0-1 are the state code and must be alphabetic.
ALPHA_PREFIX_END_INDEX = 2
# Positions 2-3 are the district code and must be numeric.
NUMERIC_DISTRICT_END_INDEX = 4
# The final 4 characters are the serial number and must be numeric.
NUMERIC_SUFFIX_LENGTH = 4

# The plate cannot be shorter than 2 letters + 1 digit + 4 digits.
MIN_PLATE_LENGTH = 7
# ...nor longer than 2 letters + 2 digits + 3 letters + 4 digits.
MAX_PLATE_LENGTH = 11

# Digit seen where a letter belongs.
DIGIT_TO_ALPHA = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"}
# Letter seen where a digit belongs.
ALPHA_TO_DIGIT = {"O": "0", "I": "1", "S": "5", "B": "8", "Z": "2"}

_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]")


def strip_separators(raw_text: str) -> str:
    """Uppercase and remove everything that is not a letter or digit.

    Handles the separators a plate legitimately carries (spaces, hyphens, dots)
    and the junk OCR invents around them (tildes, pipes, brackets) in one pass.

    Args:
        raw_text: Text exactly as OCR returned it.

    Returns:
        Uppercased text containing only A-Z and 0-9.
    """
    return _NON_ALPHANUMERIC.sub("", raw_text.upper())


def apply_positional_confusions(stripped_text: str) -> str:
    """Correct look-alike characters according to the position they occupy.

    Args:
        stripped_text: Uppercased, separator-free candidate text.

    Returns:
        The text with each confusable character resolved in the direction its
        position requires. Characters outside the confusion map, and positions
        with no fixed class, are left untouched.
    """
    length = len(stripped_text)
    characters = list(stripped_text)
    suffix_start_index = length - NUMERIC_SUFFIX_LENGTH

    for index, character in enumerate(characters):
        is_alpha_position = index < ALPHA_PREFIX_END_INDEX
        is_district_position = ALPHA_PREFIX_END_INDEX <= index < NUMERIC_DISTRICT_END_INDEX
        is_serial_position = index >= suffix_start_index

        if is_alpha_position:
            characters[index] = DIGIT_TO_ALPHA.get(character, character)
        elif is_district_position or is_serial_position:
            # The district and the serial are both numeric runs. The letter
            # series between them is not, so it is deliberately left alone.
            characters[index] = ALPHA_TO_DIGIT.get(character, character)

    return "".join(characters)


def is_valid_plate(candidate_text: str) -> bool:
    """Check a normalised plate against the format in schema.md section 3.6.

    Args:
        candidate_text: A normalised candidate.

    Returns:
        True if it matches the Indian civilian plate pattern.
    """
    return PLATE_PATTERN.fullmatch(candidate_text) is not None


def normalize_plate(raw_text: str | None, ocr_confidence: float) -> tuple[str | None, float]:
    """Normalise an OCR plate read and validate it.

    Pure: no logging, no I/O, no exceptions. An unreadable plate is an ordinary
    result, so it comes back as None rather than as a raised error.

    Args:
        raw_text: Text as OCR returned it, or None if OCR read nothing.
        ocr_confidence: The engine's confidence in that read, 0.0 to 1.0.

    Returns:
        `(normalised_plate, confidence)` when the text resolves to a valid
        plate, otherwise `(None, confidence)`. The confidence is passed through
        unchanged in both cases: it describes how well OCR read the characters,
        and normalisation does not add or remove evidence about that.
    """
    if raw_text is None:
        return None, ocr_confidence

    stripped = strip_separators(raw_text)

    # Reject on length before correcting. Applying positional rules to a string
    # of the wrong length would rewrite characters using position meanings that
    # do not apply to it, and could manufacture a valid-looking plate from noise.
    if not (MIN_PLATE_LENGTH <= len(stripped) <= MAX_PLATE_LENGTH):
        return None, ocr_confidence

    corrected = apply_positional_confusions(stripped)

    if not is_valid_plate(corrected):
        return None, ocr_confidence

    return corrected, ocr_confidence
