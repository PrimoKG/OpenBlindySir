"""Conservative title cleanup. The host may override ambiguous file metadata."""

import re

from openblindysir_server.game.state import Metadata, SessionState, TrackRef

DECORATION = re.compile(
    r"\s*[\[(](?:official\s+)?(?:lyrics?(?:\s+video)?|music\s+video|audio|video|clip\s+officiel|official\s+video)[\])]",
    re.IGNORECASE,
)


def musical_metadata(s: SessionState, ref: TrackRef) -> Metadata:
    """Inherit absent values; an explicit clear also blocks tag/filename fallbacks."""
    manual = s.metadata.get(ref, Metadata())
    imported = s.imported_metadata.get(ref, Metadata())
    cleared = set(manual.cleared_fields or []) | {
        key for key in imported.cleared_fields or [] if not getattr(manual, key, None)
    }
    aliases = manual.aliases if manual.aliases is not None else imported.aliases
    return Metadata(
        cleared_fields=sorted(cleared),
        aliases={key: values for key, values in aliases.items() if key not in cleared}
        if aliases is not None
        else None,
        tags=manual.tags if manual.tags is not None else imported.tags,
        linked_to=manual.linked_to if manual.linked_to is not None else imported.linked_to,
        enabled=manual.enabled if manual.enabled is not None else imported.enabled,
        **{
            field: None if field in cleared else getattr(manual, field) or getattr(imported, field)
            for field in ("title", "artist", "featuring", "album", "year")
        },
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
