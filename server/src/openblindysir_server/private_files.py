"""Private snapshot writes without predictable temporary names or inherited read ACLs."""

import csv
import os
import re
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate private JSON field")
        result[key] = value
    return result


def require_unlinked_path(path: Path) -> None:
    absolute = path.absolute()
    if any(p.is_symlink() or p.is_junction() for p in (absolute, *absolute.parents)):
        raise ValueError("snapshot path must not contain a link or junction")


def protect_file(path: Path) -> None:
    if os.name == "posix":
        path.chmod(0o600)
    elif os.name == "nt":
        system = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"
        result = subprocess.run(  # noqa: S603 - fixed system executable/argv
            [str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            creationflags=0x08000000,
        )
        sid = next(iter(csv.reader(result.stdout.splitlines())))[-1]
        if not re.fullmatch(r"S-1-(?:\d+-)+\d+", sid):
            raise OSError("private snapshot permissions unavailable")
        subprocess.run(  # noqa: S603 - SID validated, path is an argv item
            [str(system / "icacls.exe"), str(path), "/inheritance:r", "/grant:r", f"*{sid}:F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=10,
            creationflags=0x08000000,
        )


def private_temporary(directory: Path, data: bytes) -> Path:
    path = directory / f".snapshot-{uuid.uuid4().hex}.tmp"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        protect_file(path)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise
    return path


def atomic_private_write(path: Path, data: bytes) -> None:
    require_unlinked_path(path)
    temporary = private_temporary(path.parent, data)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def create_private_file(path: Path, data: bytes) -> None:
    """Publish a complete private file without replacing even a concurrent creation."""
    require_unlinked_path(path)
    temporary = private_temporary(path.parent, data)
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def private_file_lock(path: Path) -> Iterator[None]:
    """Nonblocking process lock; keep the sidecar inode stable, including after exits."""
    require_unlinked_path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    require_unlinked_path(lock)
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        protect_file(lock)
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415 - Windows only

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        elif os.name == "posix":
            import fcntl  # noqa: PLC0415 - Unix only

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            raise OSError("private file locking unavailable")
        yield
    finally:
        # Closing (or process termination) releases the OS lock; never unlink its file.
        os.close(descriptor)
