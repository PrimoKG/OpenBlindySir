"""Nickname and answer normalisation (spec §7.4, §12)."""

import pytest

from openblindysir_protocol.text import nickname_key, normalize_answer, normalize_nickname

ZERO_WIDTH_SPACE = chr(0x200B)
RIGHT_TO_LEFT_OVERRIDE = chr(0x202E)
BYTE_ORDER_MARK = chr(0xFEFF)
LINE_SEPARATOR = chr(0x2028)
COMBINING_ACUTE = chr(0x0301)


def fullwidth(text: str) -> str:
    """Fullwidth form of ASCII letters (U+FF41 for 'a'), folded by NFKC."""
    return "".join(chr(ord(char) - ord("a") + 0xFF41) if char.isalpha() else char for char in text)


def test_nickname_nfkc_and_whitespace() -> None:
    assert normalize_nickname(f"  {fullwidth('full')}   width ") == "full width"


def test_nickname_key_is_case_insensitive() -> None:
    assert nickname_key("Ayoub") == nickname_key("AYOUB") == nickname_key(fullwidth("ayoub"))


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "a" * 25,
        f"evil{RIGHT_TO_LEFT_OVERRIDE}boy",
        f"zero{ZERO_WIDTH_SPACE}width",
        f"bom{BYTE_ORDER_MARK}",
        "ctrl\x07",
        f"line{LINE_SEPARATOR}sep",
        "new\nline",
    ],
)
def test_nickname_refused(raw: str) -> None:
    with pytest.raises(ValueError, match="nickname_invalid"):
        normalize_nickname(raw)


def test_nickname_24_chars_accepted() -> None:
    assert normalize_nickname("a" * 24) == "a" * 24


def test_nickname_nfd_equals_nfc_key() -> None:
    assert nickname_key(f"Ame{COMBINING_ACUTE}lie") == nickname_key("Amélie")


def test_answer_strips_format_and_controls() -> None:
    raw = f" Poke{COMBINING_ACUTE}mon{ZERO_WIDTH_SPACE}\tRoute 1 "
    assert normalize_answer(raw) == "Pokémon Route 1"


def test_answer_empty_is_valid() -> None:
    assert normalize_answer("   ") == ""


def test_answer_too_long() -> None:
    with pytest.raises(ValueError, match="too_long"):
        normalize_answer("x" * 11, max_chars=10)
