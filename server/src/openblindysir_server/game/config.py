"""Bounds of the game core, frozen at start-up from the environment (spec §15)."""

from dataclasses import dataclass

from openblindysir_protocol.enums import ClipFormat


@dataclass(frozen=True, slots=True)
class CoreConfig:
    max_players: int = 20
    clip_min_s: int = 5
    clip_max_s: int = 60
    clip_format: ClipFormat = ClipFormat.AAC
    bitrate_kbps: int = 128
    max_clip_bytes: int = 2 * 1024 * 1024
    answer_max_chars: int = 200
    near_tie_ms: int = 300
    ready_timeout_ms: int = 10_000
    lead_ms: int = 3_000  # countdown before the first play (spec §9.5)
    replay_lead_ms: int = 1_500  # minimum lead allowed by spec §9.5
    add_time_ms: int = 15_000  # spec §6.1
    job_timeout_ms: int = 120_000  # above the Bridge's own 10 + 30 + 60 s timeouts
    max_track_attempts: int = 3  # spec §7.2
    max_same_track_retries: int = 1  # spec §7.6: one retry, then replacement
    decode_failure_majority: float = 0.5  # spec §12: "si la majorité des clients échoue"
    mc_upcoming_queue_heads: int = 3
