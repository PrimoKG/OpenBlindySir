"""Container entry point; preserve the existing Bridge CLI for maintenance commands."""

import os
import sys

from openblindysir_bridge.cli import main

if __name__ == "__main__":
    arguments = sys.argv[1:]
    if not arguments and os.environ.get("OPENBLINDYSIR_BRIDGE_DEMO", "false") == "true":
        arguments = ["--demo"]
    raise SystemExit(main(arguments))
