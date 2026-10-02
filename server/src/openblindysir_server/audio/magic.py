"""Container signature checks of uploaded clips (spec §5.3)."""

from openblindysir_protocol.enums import ClipFormat

MIME = {ClipFormat.AAC: "audio/mp4", ClipFormat.OPUS: "audio/webm"}
EBML = b"\x1a\x45\xdf\xa3"


def sniff_magic(fmt: ClipFormat, head: bytes) -> bool:
    """MP4 (``ftyp`` box) for AAC; WebM (EBML header) or Ogg (``OggS``) for Opus."""
    if fmt is ClipFormat.AAC:
        return len(head) >= 8 and head[4:8] == b"ftyp"
    return head.startswith((EBML, b"OggS"))


def mime_for(fmt: ClipFormat, head: bytes) -> str:
    if fmt is ClipFormat.OPUS and head.startswith(b"OggS"):
        return "audio/ogg"
    return MIME[fmt]
