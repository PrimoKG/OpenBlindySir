"""Private temporary directories with process ownership, safe across Bridge instances."""

import ctypes
import os
import shutil
import tempfile
from pathlib import Path

from openblindysir_bridge.ffmpeg import is_own_tempdir, private_tempdir_prefix

OWNER = "owner.pid"


def create(kind: str = "") -> Path:
    path = Path(tempfile.mkdtemp(prefix=private_tempdir_prefix() + kind))
    (path / OWNER).write_text(str(os.getpid()), encoding="ascii")
    return path


def process_running(pid: int) -> bool:
    if pid <= 0:
        return True
    if os.name == "nt":
        # os.kill(pid, 0) is not a safe process probe on Windows.
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, 0, pid)
        if not handle:
            # Access denied or another unknown state: keep the directory conservatively.
            return ctypes.get_last_error() != 87
        code = ctypes.c_uint32()
        try:
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def purge(root: Path) -> int:
    root = root.resolve()
    failures = 0
    for path in root.glob(private_tempdir_prefix() + "*"):
        try:
            if path.is_symlink() or path.is_junction() or path.resolve().parent != root:
                continue
            if not is_own_tempdir(path):
                continue
            owner = path / OWNER
            # Unmarked legacy directories cannot be proven idle; never delete them here.
            if owner.is_symlink() or not owner.is_file():
                continue
            pid = int(owner.read_text(encoding="ascii"))
            if process_running(pid):
                continue
            shutil.rmtree(path)
        except (OSError, ValueError):
            failures += 1
    return failures
