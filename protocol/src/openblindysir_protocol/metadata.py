"""Versioned optional musical metadata; rows are validated independently on import."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from openblindysir_protocol.base import BridgeId, InboundModel
from openblindysir_protocol.settings import check_relative_path

Text = Annotated[str, StringConstraints(max_length=256)]
AliasField = Literal["title", "artist", "album", "featuring"]
Aliases = Annotated[
    dict[AliasField, Annotated[list[Text], Field(max_length=8)]], Field(max_length=4)
]


class MusicalMetadata(InboundModel):
    cleared_fields: (
        Annotated[
            list[Literal["title", "artist", "album", "featuring", "year"]], Field(max_length=5)
        ]
        | None
    ) = None
    aliases: Aliases | None = None
    title: Text | None = None
    artist: Text | None = None
    featuring: Text | None = None
    album: Text | None = None
    year: Annotated[int, Field(ge=1000, le=9999)] | None = None
    genres: Annotated[list[Text], Field(max_length=32)] | None = None
    languages: Annotated[list[Text], Field(max_length=32)] | None = None
    tags: Annotated[list[Text], Field(max_length=32)] | None = None
    linked_to: Annotated[list[Text], Field(max_length=32)] | None = None
    enabled: bool | None = None

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, values: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        if values is None:
            return None
        return {key: cls._labels(labels) or [] for key, labels in values.items()}

    @field_validator("tags", "linked_to", "genres", "languages")
    @classmethod
    def _labels(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        labels: dict[str, str] = {}
        for value in values:
            label = cls._text(value)
            if label:
                labels.setdefault(label.casefold(), label)
        return list(labels.values())

    @field_validator("title", "artist", "featuring", "album")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("control characters are forbidden")
        return value.strip() or None


class MetadataRow(MusicalMetadata):
    bridge_id: BridgeId
    relpath: Annotated[str, StringConstraints(min_length=1, max_length=1024)]

    @field_validator("relpath")
    @classmethod
    def _relative(cls, value: str) -> str:
        return check_relative_path(value, allow_empty=False)


class MetadataDocument(InboundModel):
    version: Literal[1, 2, 3]
    rows: Annotated[list[MetadataRow], Field(max_length=10000)]
