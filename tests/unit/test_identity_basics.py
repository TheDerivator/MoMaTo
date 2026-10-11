"""Usernames, passwords and proxy handling: small pure pieces of the identity layer."""

import pytest

from momato.api.client import TrustedProxies, _host  # pyright: ignore[reportPrivateUsage]
from momato.domain.usernames import MAX_LENGTH, base_username, unique_username
from momato.identity.passwords import (
    MIN_PASSWORD_LENGTH,
    generate_password,
    hash_password,
    needs_rehash,
    password_problems,
    verify_password,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Anna Claes", "anna.claes"),
        ("Chloé Martens", "chloe.martens"),
        ("Tomás Rivera", "tomas.rivera"),
        ("Zoë Hoffman", "zoe.hoffman"),
        ("Hannes Van den Berg", "hannes.van.den.berg"),
        ("Søren Ångström", "soren.angstrom"),
        ("  O'Brien--Smith  ", "o.brien.smith"),
        ("Strauß", "strauss"),
        ("日本語", "user"),
        ("", "user"),
    ],
)
def test_usernames_are_ascii_lowercase_words(name: str, expected: str) -> None:
    assert base_username(name) == expected


def test_a_very_long_name_is_cut() -> None:
    assert len(base_username("a" * 300)) == MAX_LENGTH


def test_taken_usernames_get_a_number() -> None:
    taken = {"anna.claes", "anna.claes-2"}
    assert unique_username("Anna Claes", taken) == "anna.claes-3"
    assert unique_username("Bram Peeters", taken) == "bram.peeters"


def test_passwords_hash_verify_and_reject() -> None:
    hashed = hash_password("correct horse battery")
    assert hashed != "correct horse battery"
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse battery")
    assert not verify_password(hashed, "wrong horse battery")
    assert not verify_password(None, "anything")  # accounts without a password
    assert not verify_password("not a hash", "anything")
    assert not needs_rehash(hashed)


def test_generated_passwords_are_long_and_different() -> None:
    first, second = generate_password(), generate_password()
    assert first != second
    assert len(first) >= MIN_PASSWORD_LENGTH
    assert password_problems(first) == []


def test_password_rules() -> None:
    assert password_problems("long enough!") == []
    assert password_problems("short") == [f"must be at least {MIN_PASSWORD_LENGTH} characters"]
    assert password_problems(" padded password") == ["must not start or end with spaces"]
    assert len(password_problems(" x ")) == 2


def test_trusted_proxies_accept_addresses_networks_and_names() -> None:
    trusted = TrustedProxies("127.0.0.1, ::1, 10.0.0.0/8, testclient")
    assert "127.0.0.1" in trusted
    assert "::1" in trusted
    assert "10.4.5.6" in trusted
    assert "TestClient" in trusted
    assert "::ffff:127.0.0.1" in trusted  # a dual-stack socket
    assert "192.168.1.1" not in trusted
    assert "" not in trusted
    assert None not in trusted


def test_an_empty_list_trusts_nobody() -> None:
    assert "127.0.0.1" not in TrustedProxies("")


@pytest.mark.parametrize(
    ("entry", "host"),
    [
        ("203.0.113.5", "203.0.113.5"),
        ("203.0.113.5:51234", "203.0.113.5"),
        ("[2001:db8::1]:51234", "2001:db8::1"),
        ("2001:db8::1", "2001:db8::1"),
        ("  198.51.100.7  ", "198.51.100.7"),
    ],
)
def test_forwarded_entries_lose_their_port(entry: str, host: str) -> None:
    assert _host(entry) == host
