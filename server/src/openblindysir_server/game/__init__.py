"""Pure, synchronous game core: no IO, no asyncio, injected clock and identifiers."""

from openblindysir_server.game import commands, effects
from openblindysir_server.game.clock import Clock, FakeClock, Instant, MonotonicClock
from openblindysir_server.game.config import CoreConfig
from openblindysir_server.game.engine import GameEngine
from openblindysir_server.game.ids import IdFactory, SecretIds, SequentialIds

__all__ = [
    "Clock",
    "CoreConfig",
    "FakeClock",
    "GameEngine",
    "IdFactory",
    "Instant",
    "MonotonicClock",
    "SecretIds",
    "SequentialIds",
    "commands",
    "effects",
]
