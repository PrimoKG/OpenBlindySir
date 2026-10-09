"""Conservative title cleanup. The host may override ambiguous file metadata."""

import re
from copy import deepcopy
from dataclasses import replace

from openblindysir_server.game.state import AssetRecord, Metadata, SessionState, TrackRef
from openblindysir_server.game.themes import GENRE_LABELS, LANGUAGES, search_key

DECORATION = re.compile(
    r"\s*[\[(](?:official\s+)?(?:lyrics?(?:\s+video)?|music\s+video|audio|video|clip\s+officiel|official\s+video)[\])]",
    re.IGNORECASE,
)


def measured_tracks(s: SessionState) -> dict[TrackRef, AssetRecord]:
    """The most recently measured tags remain usable after audio eviction."""
    return {a.track_ref: a for a in s.assets.values() if a.track_duration_ms is not None}


def selection_metadata(s: SessionState, ref: TrackRef, asset: AssetRecord | None) -> Metadata:
    """Resolve search/selection titles without overriding corrections or explicit clears."""
    meta = musical_metadata(s, ref)
    if asset is None:
        return meta
    return replace(
        meta,
        **{
            key: None
            if key in (meta.cleared_fields or [])
            else getattr(meta, key) or getattr(asset, key)
            for key in ("title", "artist", "album", "year", "featuring")
        },
    )


def scoring_metadata(s: SessionState, ref: TrackRef, asset: AssetRecord | None) -> Metadata:
    """Shared by draft preflight and grading; filenames are never scoring references."""
    meta = musical_metadata(s, ref)
    resolved = selection_metadata(s, ref, asset)
    title, artist = clean_metadata(resolved.title, resolved.artist, "")
    return Metadata(
        title=None if "title" in (meta.cleared_fields or []) else meta.title or title or None,
        artist=None if "artist" in (meta.cleared_fields or []) else meta.artist or artist,
        album=resolved.album,
        year=resolved.year,
        featuring=resolved.featuring,
        aliases=deepcopy(meta.aliases),
    )


def musical_metadata(s: SessionState, ref: TrackRef) -> Metadata:
    """Inherit absent values; an explicit clear also blocks tag/filename fallbacks."""
    manual = s.metadata.get(ref, Metadata())
    imported = s.imported_metadata.get(ref, Metadata())
    catalog = s.catalogs.get(ref.bridge_id)
    entry = catalog.entries.get(ref.track_id) if catalog else None
    embedded = entry.tags if entry and entry.tags else Metadata()
    imported = replace(
        imported,
        **{
            key: getattr(imported, key) or getattr(embedded, key)
            for key in ("title", "artist", "album", "year", "featuring")
            if key not in (imported.cleared_fields or [])
        },
    )
    cleared = set(manual.cleared_fields or []) | {
        key for key in imported.cleared_fields or [] if not getattr(manual, key, None)
    }
    aliases = manual.aliases if manual.aliases is not None else imported.aliases
    tags = manual.tags if manual.tags is not None else imported.tags
    genres = manual.genres if manual.genres is not None else imported.genres
    languages = manual.languages if manual.languages is not None else imported.languages
    if genres is None:
        genres = (
            list(
                dict.fromkeys(
                    GENRE_LABELS[search_key(v)] for v in tags or [] if search_key(v) in GENRE_LABELS
                )
            )
            or None
        )
    if languages is None:
        languages = (
            list(
                dict.fromkeys(
                    LANGUAGES[search_key(v)] for v in tags or [] if search_key(v) in LANGUAGES
                )
            )
            or None
        )
    return Metadata(
        cleared_fields=sorted(cleared),
        aliases={key: values for key, values in aliases.items() if key not in cleared}
        if aliases is not None
        else None,
        tags=tags,
        genres=genres,
        languages=languages,
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
