"""PyInstaller entry point; the frozen app uses the same CLI as uvx."""

from openblindysir_bridge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
