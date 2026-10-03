"""Versioned optional musical metadata; rows are validated independently on import."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from openblindysir_protocol.base import BridgeId, InboundModel
from openblindysir_protocol.settings import check_relative_path

Text = Annotated[str, StringConstraints(max_length=256)]


class MusicalMetadata(InboundModel):
    title: Text | None = None
    artist: Text | None = None
    featuring: Text | None = None
    album: Text | None = None
    year: Annotated[int, Field(ge=1000, le=9999)] | None = None

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
    version: Literal[1]
    rows: Annotated[list[MetadataRow], Field(max_length=10000)]
