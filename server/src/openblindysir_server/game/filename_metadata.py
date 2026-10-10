"""Local filename hints for missing musical fields; never invent album or year."""

import posixpath
import re
import unicodedata

from openblindysir_server.game.state import Metadata

EXTENSION = re.compile(r"\.(?:mp3|flac|wav|m4a|aac|ogg|opus|mp4|flv|wma|aiff?)$", re.I)
BRACKET = re.compile(r"\s*[\[(]([^\])]{0,256})[\])]")
DECORATION = re.compile(
    r"\b(?:official|officiel|lyrics?|paroles|music\s*video|audio|visuali[sz]er|hd|4k|1080p|720p)\b",
    re.I,
)
TRAILER = re.compile(
    r"\s+[-\u2013\u2014|]\s+(?:(?:official|exclusive)\s+)?"
    r"(?:music\s+video|lyrics?(?:\s+video)?|audio|video\s+officiel|clip\s+officiel)\s*$",
    re.I,
)
FEATURE = re.compile(r"(?:\s|^|[\[(])(?:feat\.?|ft\.?|featuring)\s+(.+)$", re.I)


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t-\u2013\u2014|,;")[:256]


def _feature(value: str) -> tuple[str, str | None]:
    match = FEATURE.search(value)
    if not match:
        return value, None
    # Preserve a meaningful title suffix following a parenthesized guest credit.
    guest = match.group(1)
    closing = re.search(r"[\])]", guest)
    suffix = guest[closing.end() :] if closing else ""
    return _text(value[: match.start()] + " " + suffix), _text(
        guest[: closing.start()] if closing else guest
    ) or None


def filename_metadata(filename: str) -> Metadata:
    """Recognize Artist - Title (feat. Guest); a bare title supplies no artist."""
    name = posixpath.basename(filename.replace("\\", "/"))
    text = unicodedata.normalize("NFKC", EXTENSION.sub("", name)).replace("_", " ")
    text = re.sub(r"^[0-9]{1,3}[.)\s-]+(?=\D)", "", text)
    text = BRACKET.sub(lambda m: "" if DECORATION.search(m.group(1)) else m.group(), text)
    text = _text(TRAILER.sub("", text))
    parts = re.split(r"\s+[-\u2013\u2014|]\s+", text, maxsplit=1)
    # An unspaced dash may belong to the title (Couleur-café); keep it intact.
    artist = None
    guests: list[str] = []
    if len(parts) == 2:
        artist, text = map(_text, parts)
        artist, guest = _feature(artist)
        if guest:
            guests.append(guest)
    text, guest = _feature(text)
    if guest:
        guests.append(guest)
    if (
        not text
        or re.fullmatch(r"(?:track|piste|audio|unknown|untitled)[\s-]*\d*", text, re.I)
        or re.fullmatch(r"[0-9a-f]{16,}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", text, re.I)
    ):
        return Metadata()
    return Metadata(
        title=_text(text) or None,
        artist=artist or None,
        featuring=_text(" & ".join(dict.fromkeys(guests))) or None,
    )
