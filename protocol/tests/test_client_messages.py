"""Player → server messages: strict schemas (spec §8.2, §6.3)."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from openblindysir_protocol.client import AnswerSubmit, AudioStatus, ClientMessage, Hello, Ping

CLIENT = TypeAdapter(ClientMessage)
CLOCK = {"offset": 1.5, "rtt_min": 20.0}


def parse(payload: dict[str, object]) -> object:
    return CLIENT.validate_json(json.dumps(payload))


def test_answer_submit_accepts_round_and_text() -> None:
    msg = parse({"t": "ANSWER_SUBMIT", "round_id": "r_abcd", "text": "Pokémon"})
    assert isinstance(msg, AnswerSubmit)


@pytest.mark.parametrize("field", ["ts", "client_time", "elapsed_ms", "sent_at"])
def test_answer_submit_rejects_any_timestamp_field(field: str) -> None:
    with pytest.raises(ValidationError) as info:
        parse({"t": "ANSWER_SUBMIT", "round_id": "r_abcd", "text": "x", field: 123})
    assert info.value.errors()[0]["type"] == "extra_forbidden"


def test_answer_submit_empty_text_is_not_a_schema_error() -> None:
    assert isinstance(parse({"t": "ANSWER_SUBMIT", "round_id": "r_abcd", "text": ""}), AnswerSubmit)


def test_answer_text_bounded_to_1500_chars() -> None:
    parse({"t": "ANSWER_DRAFT", "round_id": "r_abcd", "text": "a" * 1500})
    with pytest.raises(ValidationError):
        parse({"t": "ANSWER_DRAFT", "round_id": "r_abcd", "text": "a" * 1501})


def test_strict_mode_refuses_coercion() -> None:
    with pytest.raises(ValidationError):
        parse({"t": "HELLO", "client_version": "0.1.0", "protocol": "1"})
    assert isinstance(parse({"t": "HELLO", "client_version": "0.1.0", "protocol": 1}), Hello)


def test_ping_accepts_integer_and_rejects_nan() -> None:
    assert isinstance(parse({"t": "PING", "c": 12}), Ping)
    with pytest.raises(ValidationError):
        CLIENT.validate_json('{"t": "PING", "c": NaN}')


def test_unknown_message_type_rejected() -> None:
    with pytest.raises(ValidationError):
        parse({"t": "CHEAT", "points": 1000})


@pytest.mark.parametrize(
    ("payload", "ok"),
    [
        ({"state": "READY", "asset_id": "a_" + "x" * 22}, True),
        ({"state": "READY"}, False),
        ({"state": "LOCKED"}, True),
        ({"state": "LOCKED", "asset_id": "a_" + "x" * 22}, False),
        ({"state": "ERROR", "error": "DECODE_FAILED"}, True),
        ({"state": "ERROR"}, False),
    ],
)
def test_audio_status_consistency(payload: dict[str, object], *, ok: bool) -> None:
    message = {"t": "AUDIO_STATUS", "clock": CLOCK, **payload}
    if ok:
        assert isinstance(parse(message), AudioStatus)
    else:
        with pytest.raises(ValidationError):
            parse(message)


def test_audio_status_requires_clock() -> None:
    with pytest.raises(ValidationError):
        parse({"t": "AUDIO_STATUS", "state": "IDLE"})
