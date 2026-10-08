"""Bounded metadata packs. No archive member is extracted to the filesystem."""

import io
import json
import re
import zipfile

JSON_LIMIT = 1024 * 1024
PACK_LIMIT = 8 * JSON_LIMIT
ROW_LIMIT = 10000


def document(rows: list[dict]) -> bytes:
    return json.dumps(
        {"version": 3, "rows": rows}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def json_chunk(rows: list[dict], offset: int) -> tuple[bytes, int]:
    selected = []
    size = len(document([]))
    for row in rows[offset : offset + ROW_LIMIT]:
        cost = len(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ) + bool(selected)
        if size + cost > JSON_LIMIT:
            break
        selected.append(row)
        size += cost
    if offset < len(rows) and not selected:
        raise ValueError("metadata row exceeds import limit")
    return document(selected), offset + len(selected)


def pack(rows: list[dict], offset: int) -> tuple[bytes, int]:
    result = io.BytesIO()
    start = offset
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as archive:
        part = 1
        while offset < len(rows) or part == 1:
            content, end = json_chunk(rows, offset)
            # Bound each downloadable pack, including the central directory.
            if part > 1 and (
                result.tell() + len(content) + 65536 > PACK_LIMIT or end - start > ROW_LIMIT
            ):
                break
            archive.writestr(f"metadata-{part:06}.json", content)
            offset = end
            part += 1
            if offset >= len(rows):
                break
    return result.getvalue(), offset


def unpack(raw: bytes) -> dict:
    rows = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if not 1 <= len(members) <= 16 or len({m.filename for m in members}) != len(members):
            raise ValueError("invalid members")
        for member in members:
            total += member.file_size
            if (
                not re.fullmatch(r"metadata-\d{6}\.json", member.filename)
                or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                or member.flag_bits & 1
                or member.file_size > JSON_LIMIT
                or total > PACK_LIMIT
            ):
                raise ValueError("invalid member or decompression limit")
            with archive.open(member) as stream:
                content = stream.read(JSON_LIMIT + 1)
            if len(content) > JSON_LIMIT:
                raise ValueError("decompression limit")
            doc = json.loads(content)
            if (
                not isinstance(doc, dict)
                or set(doc) != {"version", "rows"}
                or type(doc["version"]) is not int
                or doc["version"] not in {1, 2, 3}
                or not isinstance(doc["rows"], list)
            ):
                raise ValueError("invalid document")
            rows.extend(doc["rows"])
            if len(rows) > ROW_LIMIT:
                raise ValueError("row limit")
    return {"version": 3, "rows": rows}
