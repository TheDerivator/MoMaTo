"""A stand-in for Windows SSPI in tests: accepts made-up Kerberos-like and NTLM-like tokens.

Like the real thing, a "Kerberos" ticket signs in with one token and ends with a last word for
the browser, and "NTLM" takes two tokens with a challenge in between.
"""

from spnego.exceptions import InvalidTokenError

NTLM_HELLO = b"NTLMSSP\x00\x01\x00\x00\x00"
NTLM_CHALLENGE = b"NTLMSSP\x00\x02\x00\x00\x00challenge"
LAST_WORD = b"mutual"
_NTLM_PROOF = b"NTLMSSP\x00\x03\x00\x00\x00"
NTLM_WRONG_PASSWORD = _NTLM_PROOF + b"?"  # a second token that Windows refuses
_TICKET = b"\x60ticket:"


def ticket(account: str) -> bytes:
    """A one-token sign-in for `account` (e.g. `CORP\\JDoe`)."""
    return _TICKET + account.encode()


def ntlm_proof(account: str) -> bytes:
    """The second NTLM token: `account` answering the challenge."""
    return _NTLM_PROOF + account.encode()


class FakeContext:
    def __init__(self) -> None:
        self.complete = False
        self.client_principal: str | None = None
        self._challenged = False

    def step(self, in_token: bytes | None = None) -> bytes | None:
        token = in_token or b""
        if token.startswith(_TICKET):
            self._finish(token[len(_TICKET) :])
            return LAST_WORD
        if token == NTLM_HELLO:
            self._challenged = True
            return NTLM_CHALLENGE
        if token.startswith(_NTLM_PROOF) and self._challenged and token != NTLM_WRONG_PASSWORD:
            self._finish(token[len(_NTLM_PROOF) :])
            return None
        # (pyright cannot see through the metaclass pyspnego builds its errors with)
        raise InvalidTokenError(context_msg="the fake SSPI refuses this token")  # pyright: ignore[reportGeneralTypeIssues]

    def _finish(self, account: bytes) -> None:
        self.complete = True
        self.client_principal = account.decode()
