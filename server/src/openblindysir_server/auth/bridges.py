"""Private, durable credentials bound to an exact Bridge UUID. No raw secrets on disk."""

import hashlib
import json
import secrets
import unicodedata
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from pathlib import Path

from openblindysir_protocol.text import normalize_nickname
from openblindysir_server.private_files import (
    atomic_private_write,
    private_file_lock,
    require_unlinked_path,
    unique_json_object,
)

MAX_REGISTRY_BYTES = 128 * 1024
MAX_CREDENTIALS = 64


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def valid_id(value: str) -> str:
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("noncanonical Bridge identity")
    return value


class BridgeCredentials:
    def __init__(
        self, path: Path | None, bootstrap: str = "", configured: tuple[tuple[str, str], ...] = ()
    ) -> None:
        self.path = path
        self._signature: tuple[int, int, int, int, int] | None = None
        self._persisted = False
        self.data: dict = {
            "version": 1,
            "bootstrap_id": None,
            "bootstrap_revoked": False,
            "bridges": {},
        }
        self.bootstrap = secret_hash(bootstrap) if bootstrap else None
        self.refresh()
        if configured:
            with self._transaction():
                for bridge_id, raw in configured:
                    if bridge_id not in self.data["bridges"]:
                        self._set(bridge_id, "Bridge", secret_hash(raw))

    def refresh(self, *, force: bool = False) -> None:
        if self.path is None:
            return
        require_unlinked_path(self.path)
        if not self.path.exists():
            if self._persisted:
                raise ValueError("Bridge credential registry disappeared")
            return
        info = self.path.stat()
        signature = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_size)
        if not force and signature == self._signature:
            return
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_REGISTRY_BYTES + 1)
            if len(raw) > MAX_REGISTRY_BYTES:
                raise ValueError("Bridge credential registry too large")
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_object)
            if (
                not isinstance(data, dict)
                or set(data) != {"version", "bootstrap_id", "bootstrap_revoked", "bridges"}
                or type(data["version"]) is not int
                or data["version"] != 1
            ):
                raise ValueError("unsupported Bridge credential registry")
            if type(data["bootstrap_revoked"]) is not bool or not isinstance(data["bridges"], dict):
                raise ValueError("invalid Bridge credential registry")
            if data["bootstrap_id"] is not None:
                valid_id(data["bootstrap_id"])
            if len(data["bridges"]) > MAX_CREDENTIALS:
                raise ValueError("too many Bridge credentials")
            known = set(data["bridges"]) | (
                {data["bootstrap_id"]} if data["bootstrap_id"] else set()
            )
            if len(known) > MAX_CREDENTIALS:
                raise ValueError("too many Bridge identities")
            hashes = set()
            for identity, row in data["bridges"].items():
                valid_id(identity)
                if (
                    not isinstance(row, dict)
                    or set(row) != {"name", "secret_hash", "revoked"}
                    or type(row["revoked"]) is not bool
                ):
                    raise ValueError("invalid Bridge credential")
                digest = row["secret_hash"]
                if (
                    not isinstance(row["name"], str)
                    or normalize_nickname(row["name"]) != row["name"]
                ):
                    raise ValueError("invalid Bridge name")
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)
                ):
                    raise ValueError("invalid Bridge credential hash")
                if digest in hashes or (
                    digest == self.bootstrap and data["bootstrap_id"] != identity
                ):
                    raise ValueError("Bridge credentials must be distinct")
                hashes.add(digest)
        except (TypeError, KeyError, RecursionError) as exc:
            raise ValueError("invalid Bridge credential registry") from exc
        self.data = data
        self._signature = signature
        self._persisted = True

    def _save(self) -> None:
        if self.path is None:
            return
        require_unlinked_path(self.path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_private_write(self.path, json.dumps(self.data, ensure_ascii=False).encode("utf-8"))
        self._persisted = True
        self._signature = None

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        lock = private_file_lock(self.path) if self.path is not None else nullcontext()
        with lock:
            # The CLI and the live host API can both write. Reload only after locking.
            self.refresh(force=True)
            previous = self.data
            self.data = deepcopy(previous)
            try:
                yield
                if self.data != previous:
                    self._save()
            except BaseException:
                self.data = previous
                # A failure can occur after replacement; authentication must reread disk.
                self._signature = None
                raise

    def recognizes(self, raw: str) -> bool:
        self.refresh()
        digest = secret_hash(raw)
        return any(
            not row["revoked"] and secrets.compare_digest(digest, row["secret_hash"])
            for row in self.data["bridges"].values()
        ) or (
            self.bootstrap is not None
            and not self.data["bootstrap_revoked"]
            and secrets.compare_digest(digest, self.bootstrap)
        )

    def authorize(self, bridge_id: str, raw: str, *, bind: bool = False) -> bool:
        if bind:
            with self._transaction():
                return self._authorize(bridge_id, raw, bind=True)
        self.refresh()
        return self._authorize(bridge_id, raw, bind=False)

    def _authorize(self, bridge_id: str, raw: str, *, bind: bool) -> bool:
        digest = secret_hash(raw)
        row = self.data["bridges"].get(bridge_id)
        if row is not None:
            return not row["revoked"] and secrets.compare_digest(digest, row["secret_hash"])
        if self.data["bootstrap_revoked"] or self.bootstrap is None:
            return False
        if not secrets.compare_digest(digest, self.bootstrap):
            return False
        bound = self.data["bootstrap_id"]
        if bound is not None:
            return bound == bridge_id
        if not bind:
            return False
        valid_id(bridge_id)
        if len(self.data["bridges"]) >= MAX_CREDENTIALS:
            return False
        self.data["bootstrap_id"] = bridge_id
        return True

    def active_hash(self, bridge_id: str) -> str | None:
        self.refresh()
        row = self.data["bridges"].get(bridge_id)
        if row is not None:
            return None if row["revoked"] else row["secret_hash"]
        if self.data["bootstrap_id"] == bridge_id and not self.data["bootstrap_revoked"]:
            return self.bootstrap
        return None

    def _set(self, bridge_id: str, name: str, digest: str) -> None:
        valid_id(bridge_id)
        name = normalize_nickname(name)
        rows = self.data["bridges"]
        known = set(rows) | ({self.data["bootstrap_id"]} if self.data["bootstrap_id"] else set())
        if bridge_id not in known and len(known) >= MAX_CREDENTIALS:
            raise ValueError("too many Bridge credentials")
        if any(
            identity != bridge_id and row["secret_hash"] == digest for identity, row in rows.items()
        ):
            raise ValueError("Bridge credentials must be distinct")
        if digest == self.bootstrap and self.data["bootstrap_id"] != bridge_id:
            raise ValueError("Bridge credentials must be distinct")
        rows[bridge_id] = {"name": name, "secret_hash": digest, "revoked": False}

    def replace(self, bridge_id: str, name: str, raw: str) -> None:
        if not 32 <= len(raw) <= 4096 or any(
            unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in raw
        ):
            raise ValueError("invalid Bridge secret")
        with self._transaction():
            self._set(bridge_id, name, secret_hash(raw))
            if self.data["bootstrap_id"] == bridge_id:
                self.data["bootstrap_revoked"] = True

    def revoke(self, bridge_id: str) -> bool:
        with self._transaction():
            row = self.data["bridges"].get(bridge_id)
            if row is None and self.data["bootstrap_id"] != bridge_id:
                return False
            if row is not None:
                row["revoked"] = True
            if self.data["bootstrap_id"] == bridge_id:
                self.data["bootstrap_revoked"] = True
            return True
