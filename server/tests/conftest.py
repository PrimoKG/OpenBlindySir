"""Shared test configuration: Hypothesis profiles (``HYPOTHESIS_PROFILE=ci`` in CI)."""

import os
import sys
from pathlib import Path

from hypothesis import HealthCheck, settings

sys.path.insert(0, str(Path(__file__).resolve().parent / "game"))

settings.register_profile("dev", max_examples=60, deadline=None)
settings.register_profile(
    "ci", max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
