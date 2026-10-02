"""Shared test configuration: Hypothesis profiles.

``dev`` locally, ``ci`` on every push, ``nightly`` for the long fuzzing run of the core state
machine (``HYPOTHESIS_PROFILE=nightly``). A failure found there becomes a deterministic
regression test (see ``game/test_review_regressions.py``).
"""

import os
import sys
from pathlib import Path

from hypothesis import HealthCheck, settings

sys.path.insert(0, str(Path(__file__).resolve().parent / "game"))

settings.register_profile("dev", max_examples=60, deadline=None)
settings.register_profile(
    "ci", max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile(
    "nightly",
    max_examples=3000,
    stateful_step_count=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    print_blob=True,
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
