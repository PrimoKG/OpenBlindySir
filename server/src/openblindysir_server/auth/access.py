"""Session invitations and host-approved identity transfers, separate from host login."""

import re
import secrets
from dataclasses import dataclass

from openblindysir_server.auth.sessions import hash_token, new_token
from openblindysir_server.logging import redaction


@dataclass
class Claim:
    player_id: str
    token_hash: str
    expires: int
    approved: bool = False
    requester: str = ""

    @property
    def reference(self) -> str:
        return self.token_hash[:8].upper()


class SessionAccess:
    def __init__(self) -> None:
        self.code = ""
        self.invitation = ""
        self.claims: dict[str, Claim] = {}

    def ensure(self) -> None:
        if not self.code:
            self.rotate()

    def rotate(self, code: str | None = None) -> None:
        value = code or "".join(
            secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8)
        )
        if re.fullmatch(r"[A-Z2-9]{6,16}", value) is None:
            raise ValueError("invalid session code")
        self.code, self.invitation = value, new_token()
        self.claims.clear()
        redaction().add_secret(value)
        redaction().add_secret(self.invitation)

    def valid(self, code: str, invitation: str) -> bool:
        # Both formats are ASCII; reject malformed input before constant-time comparison.
        valid_code = re.fullmatch(r"[A-Z2-9]{6,16}", code) is not None
        valid_invitation = re.fullmatch(r"[A-Za-z0-9_-]{43}", invitation) is not None
        return bool(valid_code and self.code and secrets.compare_digest(code, self.code)) or bool(
            valid_invitation
            and self.invitation
            and secrets.compare_digest(invitation, self.invitation)
        )

    def prune(self, now: int) -> None:
        self.claims = {key: claim for key, claim in self.claims.items() if claim.expires > now}

    def claim(
        self, player_id: str, now: int, requester: str = "", *, capacity: int = 32
    ) -> tuple[str, str]:
        self.prune(now)
        # Two browsers can legitimately request one identity. Further requests cannot
        # replace either request or exhaust slots intended for other identities.
        if (
            len(self.claims) >= capacity
            or sum(c.player_id == player_id for c in self.claims.values()) >= 2
            or sum(c.requester == requester for c in self.claims.values()) >= 8
        ):
            raise ValueError("too many claims")
        token, key = new_token(), secrets.token_hex(16)
        self.claims[key] = Claim(player_id, hash_token(token), now + 120000, requester=requester)
        redaction().add_secret(token)
        return key, token

    def snapshot(self) -> dict[str, str]:
        return {"code": self.code, "invitation": self.invitation}

    def restore(self, row: dict[str, str]) -> None:
        if set(row) != {"code", "invitation"} or not all(isinstance(v, str) for v in row.values()):
            raise ValueError("invalid session access")
        if row["code"] and re.fullmatch(r"[A-Z2-9]{6,16}", row["code"]) is None:
            raise ValueError("invalid session access code")
        if bool(row["code"]) != bool(row["invitation"]) or len(row["invitation"]) > 64:
            raise ValueError("invalid session invitation")
        self.code, self.invitation = row["code"], row["invitation"]
        self.claims.clear()
        if self.code:
            redaction().add_secret(self.code)
            redaction().add_secret(self.invitation)
