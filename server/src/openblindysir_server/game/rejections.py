"""Command rejection: handlers validate everything before any mutation."""

from openblindysir_protocol.errors import ErrorCode


class Rejected(Exception):
    """A command refused with a protocol error code; the state is left unchanged."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def require(condition: bool, code: ErrorCode) -> None:
    if not condition:
        raise Rejected(code)
