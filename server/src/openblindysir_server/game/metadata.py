"""Conservative title cleanup. The host may override ambiguous file metadata."""

import re

DECORATION = re.compile(
    r"\s*[\[(](?:official\s+)?(?:lyrics?(?:\s+video)?|music\s+video|audio|video|clip\s+officiel|official\s+video)[\])]",
    re.IGNORECASE,
)


def clean_metadata(title: str | None, artist: str | None, fallback: str) -> tuple[str, str | None]:
    text = DECORATION.sub("", title or fallback).strip()
    parts = re.split(r"\s+[\u2014\u2013-]\s+", text, maxsplit=1)
    if len(parts) == 2:
        candidate, song = parts
        # A common exporter puts the full "artist - title" string in the title tag.
        if not artist or artist.casefold() in candidate.casefold():
            artist, text = candidate, song
    return text or fallback, artist
