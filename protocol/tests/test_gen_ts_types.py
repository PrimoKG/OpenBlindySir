"""Golden tests of the in-house JSON Schema → TypeScript converter."""

import pytest

import gen_ts_types

MINI = {
    "$defs": {
        "Kind": {"enum": ["a", "b"], "title": "Kind", "type": "string"},
        "Node": {
            "type": "object",
            "title": "Node",
            "properties": {
                "name": {"type": "string", "maxLength": 3, "description": "Display name"},
                "count": {"type": "integer"},
                "ratio": {"type": "number"},
                "flag": {"type": "boolean"},
                "tag": {"const": "x", "type": "string"},
                "maybe": {"anyOf": [{"$ref": "#/$defs/Node"}, {"type": "null"}]},
                "items": {"type": "array", "items": {"$ref": "#/$defs/Node"}},
                "map": {"type": "object", "additionalProperties": {"type": "integer"}},
                "opt": {"type": "string"},
            },
            "required": ["name", "count", "ratio", "flag", "tag", "maybe", "items", "map"],
        },
    },
    "roots": {"Node": {"$ref": "#/$defs/Node"}, "Either": {"oneOf": [{"type": "string"}]}},
}


def mini_output(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(gen_ts_types, "string_enums", lambda: [])
    monkeypatch.setattr(gen_ts_types, "EXPORTED_CONSTANTS", {})
    schema = {**MINI, "$defs": {k: v for k, v in MINI["$defs"].items() if k != "Kind"}}
    return gen_ts_types.generate(schema)


def test_golden_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    out = mini_output(monkeypatch)
    expected = "\n".join(
        [
            "export interface Node {",
            "  /** Display name */",
            "  readonly name: string;",
            "  readonly count: number;",
            "  readonly ratio: number;",
            "  readonly flag: boolean;",
            '  readonly tag: "x";',
            "  readonly maybe: Node | null;",
            "  readonly items: readonly Node[];",
            "  readonly map: Readonly<Record<string, number>>;",
            "  readonly opt?: string;",
            "}",
        ]
    )
    assert expected in out
    assert "export type Either = string;" in out
    assert "export type Node =" not in out


def test_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    assert mini_output(monkeypatch) == mini_output(monkeypatch)


@pytest.mark.parametrize("keyword", ["allOf", "not", "if", "patternProperties", "prefixItems"])
def test_unsupported_keyword_is_an_error(keyword: str) -> None:
    with pytest.raises(gen_ts_types.UnsupportedSchemaError):
        gen_ts_types.type_expr({keyword: []})


def test_enum_def_must_be_a_protocol_enum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen_ts_types, "string_enums", lambda: [])
    with pytest.raises(gen_ts_types.UnsupportedSchemaError):
        gen_ts_types.generate(MINI)


def test_real_protocol_generates_without_any() -> None:
    out = gen_ts_types.generate()
    assert ": any" not in out
    assert "export const PROTOCOL_VERSION = 2;" in out
    assert out.endswith("\n")
    assert "\r" not in out
