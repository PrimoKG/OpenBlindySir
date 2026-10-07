"""Nickname and answer normalisation, shared by validators and the game core (spec §12)."""

import re
import unicodedata

NICKNAME_MIN = 1
NICKNAME_MAX = 24
ANSWER_HARD_MAX = 1500

# Control, format (zero-width, bidi overrides), surrogate, private-use and unassigned
# characters, and line/paragraph separators, are refused in nicknames.
_NICKNAME_FORBIDDEN = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_ANSWER_DROPPED = frozenset({"Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_SPACES = re.compile(r"[ \t]+")


def normalize_nickname(raw: str) -> str:
    """Return the canonical nickname or raise ``ValueError("nickname_invalid")``.

    NFKC, trimmed, runs of spaces/tabs collapsed to one space; 1 to 24 characters; no
    control, format (zero-width, bidi), surrogate, private-use or unassigned character.
    """
    text = _SPACES.sub(" ", unicodedata.normalize("NFKC", raw)).strip()
    if any(unicodedata.category(char) in _NICKNAME_FORBIDDEN for char in text):
        raise ValueError("nickname_invalid")
    if not NICKNAME_MIN <= len(text) <= NICKNAME_MAX:
        raise ValueError("nickname_invalid")
    return text


def nickname_key(nickname: str) -> str:
    """Uniqueness key of a nickname: case-insensitive comparison after NFKC."""
    return normalize_nickname(nickname).casefold()


def normalize_answer(raw: str, max_chars: int = ANSWER_HARD_MAX) -> str:
    """Return the canonical answer text or raise ``ValueError("too_long")``.

    NFC; control characters become spaces; format, surrogate, private-use, unassigned and
    line/paragraph separator characters are removed; edges are trimmed. Empty is valid.
    """
    if max_chars > ANSWER_HARD_MAX:
        raise ValueError("max_chars above the hard maximum")
    kept: list[str] = []
    for char in unicodedata.normalize("NFC", raw):
        category = unicodedata.category(char)
        if category == "Cc":
            kept.append(" ")
        elif category not in _ANSWER_DROPPED:
            kept.append(char)
    result = "".join(kept).strip()
    if len(result) > max_chars:
        raise ValueError("too_long")
    return result
