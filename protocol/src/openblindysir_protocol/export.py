"""JSON Schema export of the protocol: input of the TS generator and of the schema lock."""

import hashlib
import json
from typing import Any, Final, Literal

from pydantic import TypeAdapter

from openblindysir_protocol.bridge import BridgeToServer, CatalogUpload, ServerToBridge
from openblindysir_protocol.client import ClientMessage
from openblindysir_protocol.compatibility import Compatibility
from openblindysir_protocol.diagnostics import DiagnosticsResponse
from openblindysir_protocol.host_commands import HostCommand
from openblindysir_protocol.http import (
    ConfirmRequest,
    ErrorResponse,
    HealthResponse,
    HostElevateRequest,
    HostElevateResponse,
    JoinRequest,
    JoinResponse,
    LibraryResponse,
    LibrarySearch,
    MetadataEdit,
    OkResponse,
    RecoveryCode,
    RecoveryRequest,
    SelectionPreview,
    SelectionPreviewRequest,
    SessionResponse,
    SourceUpdate,
)
from openblindysir_protocol.server import ServerMessage
from openblindysir_protocol.settings import WS_PLAYER_MAX_BYTES
from openblindysir_protocol.text import ANSWER_HARD_MAX, NICKNAME_MAX
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_protocol.views import (
    GameRecord,
    HistoryResponse,
    HostMcView,
    HostPlayerModeView,
    PlayerView,
)

Mode = Literal["validation", "serialization"]

# TS name → (type, JSON Schema mode). Inbound types use "validation", outbound "serialization".
WEB_ROOTS: Final[dict[str, tuple[Any, Mode]]] = {
    "ConfirmRequest": (ConfirmRequest, "validation"),
    "Compatibility": (Compatibility, "serialization"),
    "GameRecord": (GameRecord, "serialization"),
    "HistoryResponse": (HistoryResponse, "serialization"),
    "ClientMessage": (ClientMessage, "validation"),
    "HostCommand": (HostCommand, "validation"),
    "ServerMessage": (ServerMessage, "serialization"),
    "PlayerView": (PlayerView, "serialization"),
    "HostPlayerModeView": (HostPlayerModeView, "serialization"),
    "HostMcView": (HostMcView, "serialization"),
    "JoinRequest": (JoinRequest, "validation"),
    "JoinResponse": (JoinResponse, "serialization"),
    "SessionResponse": (SessionResponse, "serialization"),
    "HostElevateRequest": (HostElevateRequest, "validation"),
    "HostElevateResponse": (HostElevateResponse, "serialization"),
    "OkResponse": (OkResponse, "serialization"),
    "ErrorResponse": (ErrorResponse, "serialization"),
    "LibraryResponse": (LibraryResponse, "serialization"),
    "DiagnosticsResponse": (DiagnosticsResponse, "serialization"),
    "HealthResponse": (HealthResponse, "serialization"),
    "LibrarySearch": (LibrarySearch, "serialization"),
    "SelectionPreview": (SelectionPreview, "serialization"),
    "SelectionPreviewRequest": (SelectionPreviewRequest, "validation"),
    "MetadataEdit": (MetadataEdit, "validation"),
    "SourceUpdate": (SourceUpdate, "validation"),
    "RecoveryCode": (RecoveryCode, "serialization"),
    "RecoveryRequest": (RecoveryRequest, "validation"),
}
BRIDGE_ROOTS: Final[dict[str, tuple[Any, Mode]]] = {
    "BridgeToServer": (BridgeToServer, "validation"),
    "ServerToBridge": (ServerToBridge, "validation"),
    "CatalogUpload": (CatalogUpload, "validation"),
}
EXPORTED_CONSTANTS: Final[dict[str, int]] = {
    "PROTOCOL_VERSION": PROTOCOL_VERSION,
    "ANSWER_HARD_MAX": ANSWER_HARD_MAX,
    "NICKNAME_MAX": NICKNAME_MAX,
    "POINTS_BOUND": 1000,
    "WS_PLAYER_MAX_BYTES": WS_PLAYER_MAX_BYTES,
}
REF_TEMPLATE: Final = "#/$defs/{model}"


class SchemaConflictError(RuntimeError):
    """Two roots define the same ``$defs`` name with different schemas."""


def root_schema(tp: Any, mode: Mode) -> dict[str, Any]:
    """JSON Schema of one root type, with its ``$defs``."""
    return TypeAdapter(tp).json_schema(mode=mode, ref_template=REF_TEMPLATE)


def canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def web_json_schema() -> dict[str, Any]:
    """Merged schema ``{"$defs": {...}, "roots": {name: schema}}`` of every web root.

    A root that is a model is moved into ``$defs`` and referenced from ``roots``.
    """
    defs: dict[str, Any] = {}
    roots: dict[str, Any] = {}

    def add_def(name: str, schema: dict[str, Any]) -> None:
        if name in defs and canonical(defs[name]) != canonical(schema):
            raise SchemaConflictError(name)
        defs[name] = schema

    for name, (tp, mode) in WEB_ROOTS.items():
        schema = root_schema(tp, mode)
        for def_name, def_schema in schema.pop("$defs", {}).items():
            add_def(def_name, def_schema)
        if schema.get("type") == "object" and "properties" in schema:
            add_def(schema.get("title", name), schema)
            roots[name] = {"$ref": REF_TEMPLATE.format(model=schema.get("title", name))}
        else:
            roots[name] = schema
    return {"$defs": dict(sorted(defs.items())), "roots": dict(sorted(roots.items()))}


def schema_fingerprints() -> dict[str, str]:
    """``{root name: sha256(canonical JSON Schema of that root)}`` for web and Bridge roots."""
    fingerprints: dict[str, str] = {}
    for name, (tp, mode) in {**WEB_ROOTS, **BRIDGE_ROOTS}.items():
        text = canonical(root_schema(tp, mode))
        fingerprints[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return dict(sorted(fingerprints.items()))
