"""Install a complete verified backup in an offline, stopped Docker data volume."""

import argparse
import os
import shutil
import uuid
from pathlib import Path


def unlinked(path: Path) -> None:
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError("restore paths must not contain links")


def restore(source: Path, target: Path, *, directory: bool) -> None:
    source, target = source.absolute(), target.absolute()
    unlinked(source)
    unlinked(target)
    expected = "state" if directory else "config.toml"
    if target.name != expected or not target.parent.is_dir():
        raise ValueError("unexpected restore target")
    if directory:
        if not source.is_dir() or not (source / "session.json").is_file():
            raise ValueError("incomplete session backup")
        for entry in source.rglob("*"):
            unlinked(entry)
            if not entry.is_file() and not entry.is_dir():
                raise ValueError("unsupported backup entry")
    elif not source.is_file():
        raise ValueError("missing Bridge configuration")
    # Both temporary paths resolve inside the explicitly selected volume directory.
    root = target.parent.resolve(strict=True)
    stage = root / f".restore-{uuid.uuid4().hex}"
    previous = root / f".before-restore-{uuid.uuid4().hex}"
    if not all(p.resolve().parent == root for p in (target, stage, previous)):
        raise ValueError("restore outside data volume")
    try:
        if directory:
            shutil.copytree(source, stage)
            stage.chmod(0o700)
        else:
            shutil.copyfile(source, stage)
            stage.chmod(0o600)
        if target.exists():
            os.replace(target, previous)
        try:
            os.replace(stage, target)
        except BaseException:
            if previous.exists():
                os.replace(previous, target)
            raise
    finally:
        if stage.exists():
            if directory:
                shutil.rmtree(stage)
            else:
                stage.unlink()
    # Keep old contents until the replacement succeeds; do not merge obsolete files.
    if previous.exists():
        if directory:
            shutil.rmtree(previous)
        else:
            previous.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--directory", action="store_true")
    mode.add_argument("--file", action="store_true")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    restore(args.source, args.target, directory=args.directory)


if __name__ == "__main__":
    main()
