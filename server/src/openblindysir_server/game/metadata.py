"""Conservative title cleanup. The host may override ambiguous file metadata."""

import re

from openblindysir_server.game.state import Metadata, SessionState, TrackRef

DECORATION = re.compile(
    r"\s*[\[(](?:official\s+)?(?:lyrics?(?:\s+video)?|music\s+video|audio|video|clip\s+officiel|official\s+video)[\])]",
    re.IGNORECASE,
)


def musical_metadata(s: SessionState, ref: TrackRef) -> Metadata:
    """A manual non-empty field overrides import; absent fields retain imported values."""
    manual = s.metadata.get(ref, Metadata())
    imported = s.imported_metadata.get(ref, Metadata())
    return Metadata(
        **{
            field: getattr(manual, field) or getattr(imported, field)
            for field in ("title", "artist", "featuring", "album", "year")
        }
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
