"""The game core is pure and synchronous (spec §2 principle 2, §5.2): checked on the AST."""

import ast
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[2] / "src" / "openblindysir_server" / "game"
BANNED = {"asyncio", "fastapi", "starlette", "uvicorn", "websockets", "logging", "os", "socket"}
CLOCK_ONLY = {"time", "secrets"}
ALLOWED_CLOCK_FILES = {"clock.py", "ids.py"}


def modules() -> list[Path]:
    return sorted(GAME.glob("*.py"))


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_io_nor_async(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = {(node.module or "").split(".")[0]}
        else:
            names = set()
        assert not names & BANNED, f"{path.name} imports {names & BANNED}"
        if path.name not in ALLOWED_CLOCK_FILES:
            assert not names & CLOCK_ONLY, f"{path.name} reads a clock or randomness"
        assert not isinstance(node, ast.AsyncFunctionDef | ast.Await), path.name


def test_only_reveal_and_mc_builders_read_track_data() -> None:
    tree = ast.parse((GAME / "views.py").read_text(encoding="utf-8"))
    allowed = {"_reveal_track", "_mc_panel", "_mc_track_info", "_track_info"}
    for func in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        if func.name in allowed:
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {
                    "catalogs",
                    "relpath",
                    "entries",
                    "reveal",
                    "title",
                    "artist",
                }, f"{func.name} reads {node.attr}"
