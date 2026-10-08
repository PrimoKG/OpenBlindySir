"""Bounded, composable host-only selection criteria."""

from typing import Annotated

from pydantic import Field, StringConstraints, field_validator, model_validator

from openblindysir_protocol.base import InboundModel

Label = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Labels = Annotated[list[Label], Field(max_length=16)]


class ThemeFilter(InboundModel):
    query: Annotated[str, StringConstraints(max_length=256)] = ""
    genres: Labels = Field(default_factory=list)
    languages: Labels = Field(default_factory=list)
    tags: Labels = Field(default_factory=list)
    linked_to: Labels = Field(default_factory=list)
    year_min: Annotated[int, Field(ge=1000, le=9999)] | None = None
    year_max: Annotated[int, Field(ge=1000, le=9999)] | None = None

    @field_validator("query")
    @classmethod
    def _query(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("control characters are forbidden")
        return value.strip()

    @field_validator("genres", "languages", "tags", "linked_to")
    @classmethod
    def _labels(cls, values: list[str]) -> list[str]:
        labels: dict[str, str] = {}
        for value in values:
            label = cls._query(value)
            if label:
                labels.setdefault(label.casefold(), label)
        return list(labels.values())

    @model_validator(mode="after")
    def _range(self) -> "ThemeFilter":
        if (
            self.year_min is not None
            and self.year_max is not None
            and self.year_min > self.year_max
        ):
            raise ValueError("invalid year range")
        return self
