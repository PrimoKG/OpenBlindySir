"""Shared theme matching for search, previews and actual round selection."""

import re
import unicodedata
from dataclasses import dataclass, field

from openblindysir_protocol.themes import ThemeFilter
from openblindysir_server.game.state import Metadata, ThemeFilterData

LANGUAGES = {
    "francais": "fr",
    "french": "fr",
    "fra": "fr",
    "fre": "fr",
    "fr": "fr",
    "anglais": "en",
    "english": "en",
    "eng": "en",
    "en": "en",
    "japonais": "ja",
    "japanese": "ja",
    "jpn": "ja",
    "ja": "ja",
    "espagnol": "es",
    "spanish": "es",
    "espanol": "es",
    "spa": "es",
    "es": "es",
    "italien": "it",
    "italian": "it",
    "ita": "it",
    "it": "it",
    "allemand": "de",
    "german": "de",
    "deu": "de",
    "ger": "de",
    "de": "de",
    "arabe": "ar",
    "arabic": "ar",
    "ara": "ar",
    "ar": "ar",
    "instrumental": "zxx",
    "sans paroles": "zxx",
    "zxx": "zxx",
    "inconnue": "und",
    "unknown": "und",
    "und": "und",
}
GENRE_LABELS = {
    search: label
    for search, label in (
        ("pop", "Pop"),
        ("rap", "Rap"),
        ("hip hop", "Hip-Hop"),
        ("hiphop", "Hip-Hop"),
        ("rock", "Rock"),
        ("rnb", "R&B"),
        ("r b", "R&B"),
        ("jazz", "Jazz"),
        ("electro", "Electro"),
        ("electronic", "Electronic"),
        ("classique", "Classique"),
        ("classical", "Classical"),
        ("reggae", "Reggae"),
        ("metal", "Metal"),
        ("country", "Country"),
        ("soul", "Soul"),
        ("funk", "Funk"),
        ("disco", "Disco"),
        ("dance", "Dance"),
        ("blues", "Blues"),
        ("rai", "Raï"),
        ("chaabi", "Chaâbi"),
        ("k pop", "K-Pop"),
        ("j pop", "J-Pop"),
    )
}


def search_key(value: str) -> str:
    text = "".join(
        c for c in unicodedata.normalize("NFKD", value).casefold() if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^\w]+|_", " ", text).split())


def language_key(value: str) -> str:
    key = search_key(value)
    return LANGUAGES.get(key, key)


def genre_key(value: str) -> str:
    key = search_key(value)
    return {"hip hop": "rap", "hiphop": "rap", "r b": "rnb", "r n b": "rnb"}.get(key, key)


@dataclass(slots=True)
class ThemeFacets:
    labels: dict[str, dict[str, str]] = field(
        default_factory=lambda: {name: {} for name in ("genres", "languages", "tags", "linked_to")}
    )
    years: set[int] = field(default_factory=set)

    def add(self, meta: Metadata) -> None:
        for name, key in (
            ("genres", genre_key),
            ("languages", language_key),
            ("tags", search_key),
            ("linked_to", search_key),
        ):
            for value in getattr(meta, name) or (["und"] if name == "languages" else []):
                if len(self.labels[name]) < 512:
                    canonical = key(value)
                    self.labels[name].setdefault(
                        canonical, canonical if name == "languages" else value
                    )
        if meta.year is not None:
            self.years.add(meta.year)

    def values(self, name: str) -> list[str]:
        return sorted(self.labels[name].values(), key=search_key)


def matches_theme(meta: Metadata, relpath: str, theme: ThemeFilter | ThemeFilterData) -> bool:
    # Choices in one category are ORed; different categories are ANDed.
    for selected, values, key in (
        (theme.genres, meta.genres or [], genre_key),
        (theme.languages, meta.languages or ["und"], language_key),
        (theme.tags, meta.tags or [], search_key),
        (theme.linked_to, meta.linked_to or [], search_key),
    ):
        if selected and not ({key(v) for v in selected} & {key(v) for v in values}):
            return False
    if theme.year_min is not None and (meta.year is None or meta.year < theme.year_min):
        return False
    if theme.year_max is not None and (meta.year is None or meta.year > theme.year_max):
        return False
    if not theme.query:
        return True
    text = search_key(
        " ".join(
            [
                relpath,
                meta.title or "",
                meta.artist or "",
                meta.album or "",
                meta.featuring or "",
                str(meta.year or ""),
                *(meta.genres or []),
                *(genre_key(v) for v in meta.genres or []),
                *(meta.languages or []),
                *(meta.tags or []),
                *(meta.linked_to or []),
            ]
        )
    )
    language_keys = {language_key(v) for v in meta.languages or []}
    return all(
        term in text or LANGUAGES.get(term) in language_keys
        for term in search_key(theme.query).split()
    )
