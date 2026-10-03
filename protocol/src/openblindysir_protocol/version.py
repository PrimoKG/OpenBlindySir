"""Wire protocol version, exchanged in HELLO (spec §8)."""

from typing import Final

PROTOCOL_VERSION: Final[int] = 5
PROTOCOL_MIN: Final[int] = PROTOCOL_VERSION
PROTOCOL_MAX: Final[int] = PROTOCOL_VERSION
