"""Windows sign-in (Negotiate): handshakes per connection, their expiry, and the identity."""

import sys

import pytest

from momato.config import Settings
from momato.domain.errors import InvalidCredentialsError
from momato.identity.providers import negotiate
from momato.identity.providers.negotiate import HANDSHAKE_SECONDS, NegotiateProvider
from tests.fake_negotiate import (
    LAST_WORD,
    NTLM_CHALLENGE,
    NTLM_HELLO,
    NTLM_WRONG_PASSWORD,
    FakeContext,
    ntlm_proof,
    ticket,
)

JDOE = "CORP\\JDoe"
PC_1 = (("10.0.0.7", 50123), ("10.0.0.1", 8080))
PC_2 = (("10.0.0.8", 50123), ("10.0.0.1", 8080))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def provider(**options: object) -> NegotiateProvider:
    return NegotiateProvider(new_context=FakeContext, **options)  # type: ignore[arg-type]


def test_one_token_can_be_enough() -> None:
    """Kerberos: the ticket says it all, and the browser gets a last word back."""
    step = provider().step(PC_1, ticket(JDOE))
    assert step.identity is not None and step.token == LAST_WORD
    assert step.identity.provider == "windows"
    assert step.identity.subject == "corp\\jdoe"  # the full name, the stable part
    assert step.identity.username == "jdoe"  # what prepared accounts are matched on
    assert step.identity.display_name == "JDoe"
    assert step.identity.email is None and step.identity.groups == ()


def test_ntlm_takes_two_tokens_on_one_connection() -> None:
    windows = provider()
    first = windows.step(PC_1, NTLM_HELLO)
    assert first.identity is None and first.token == NTLM_CHALLENGE
    second = windows.step(PC_1, ntlm_proof(JDOE))
    assert second.identity is not None and second.identity.username == "jdoe"
    assert second.token is None


def test_handshakes_on_different_connections_do_not_mix() -> None:
    windows = provider()
    windows.step(PC_1, NTLM_HELLO)
    windows.step(PC_2, NTLM_HELLO)
    assert windows.step(PC_2, ntlm_proof("CORP\\Anna")).identity.username == "anna"  # type: ignore[union-attr]
    assert windows.step(PC_1, ntlm_proof(JDOE)).identity.username == "jdoe"  # type: ignore[union-attr]


def test_a_second_token_needs_the_handshake_it_continues() -> None:
    windows = provider()
    windows.step(PC_1, NTLM_HELLO)
    with pytest.raises(InvalidCredentialsError, match="interrupted"):
        windows.step(PC_2, ntlm_proof(JDOE))  # another connection: a proxy in between, say


def test_a_handshake_is_used_once() -> None:
    windows = provider()
    windows.step(PC_1, NTLM_HELLO)
    windows.step(PC_1, ntlm_proof(JDOE))
    with pytest.raises(InvalidCredentialsError, match="interrupted"):
        windows.step(PC_1, ntlm_proof(JDOE))


def test_a_half_finished_handshake_expires() -> None:
    clock = Clock()
    windows = provider(clock=clock)
    windows.step(PC_1, NTLM_HELLO)
    clock.now += HANDSHAKE_SECONDS + 1
    with pytest.raises(InvalidCredentialsError, match="interrupted"):
        windows.step(PC_1, ntlm_proof(JDOE))


def test_a_first_token_starts_over() -> None:
    """A connection's port can be reused: old state must not meet a new handshake."""
    windows = provider()
    windows.step(PC_1, NTLM_HELLO)
    assert windows.step(PC_1, NTLM_HELLO).token == NTLM_CHALLENGE
    assert windows.step(PC_1, ntlm_proof(JDOE)).identity is not None


def test_a_refused_token_leaves_nothing_behind() -> None:
    windows = provider()
    windows.step(PC_1, NTLM_HELLO)
    with pytest.raises(InvalidCredentialsError, match="did not accept"):
        windows.step(PC_1, NTLM_WRONG_PASSWORD)
    with pytest.raises(InvalidCredentialsError, match="interrupted"):
        windows.step(PC_1, ntlm_proof(JDOE))


def test_tokens_that_start_nothing_are_refused() -> None:
    with pytest.raises(InvalidCredentialsError):
        provider().step(PC_1, b"")
    with pytest.raises(InvalidCredentialsError):
        provider().step(PC_1, b"\x60not a ticket")


def test_only_so_many_handshakes_wait_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(negotiate, "MAX_PENDING", 2)
    windows = provider()
    for port in (1, 2, 3):
        windows.step((("10.0.0.7", port), ()), NTLM_HELLO)
    with pytest.raises(InvalidCredentialsError):  # the oldest made room
        windows.step((("10.0.0.7", 1), ()), ntlm_proof(JDOE))
    assert windows.step((("10.0.0.7", 3), ()), ntlm_proof(JDOE)).identity is not None


def test_the_domain_can_be_kept_in_the_username() -> None:
    step = provider(strip_domain=False).step(PC_1, ticket(JDOE))
    assert step.identity is not None and step.identity.username == "corp\\jdoe"


def test_kerberos_style_names_are_understood() -> None:
    step = provider().step(PC_1, ticket("JDoe@CORP.EXAMPLE"))
    assert step.identity is not None
    assert (step.identity.subject, step.identity.username) == ("jdoe@corp.example", "jdoe")


@pytest.mark.parametrize("nobody", ["", "  ", "CORP\\"])
def test_a_handshake_that_names_nobody_is_refused(nobody: str) -> None:
    with pytest.raises(InvalidCredentialsError, match="who is signing in"):
        provider().step(PC_1, ticket(nobody))


def test_it_is_refused_where_there_is_no_sspi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    settings = Settings(windows_auth=True, _env_file=None)  # pyright: ignore[reportCallIssue]
    with pytest.raises(ValueError, match="needs a Windows server"):
        NegotiateProvider.from_settings(settings)
