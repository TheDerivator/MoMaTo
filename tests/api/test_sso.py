"""Single sign-on: OpenID Connect against an in-process provider, a trusted proxy header, Windows
sign-in (Negotiate) with a fake SSPI, prepared people, policies, group mappings. [AUTH-3] [ADM-5]

A prepared person signs in and gets exactly the rights prepared; strangers follow the configured
policy; suspended and deactivated people are refused; every token and flow check is exercised.
"""

import base64
from collections.abc import Generator, Iterator, Mapping
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select, update

from momato.config import Settings, UnknownUserPolicy
from momato.db.models import (
    AuditEntry,
    ExternalIdentity,
    GroupRoleMapping,
    OrgNode,
    Role,
    RoleAssignment,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.db.session import Database
from momato.domain.access import Scope
from momato.identity.providers import (
    ExternalIdentity as Identity,
)
from momato.identity.providers import IdentityProviders
from momato.identity.providers.negotiate import NegotiateProvider
from momato.web import create_app
from momato.web.csrf import CSRF_HEADER
from tests.conftest import TEST_ADMIN_PASSWORD, start_client
from tests.fake_idp import FakeIdentityProvider, fake_oidc_provider, new_key
from tests.fake_negotiate import (
    LAST_WORD,
    NTLM_CHALLENGE,
    NTLM_HELLO,
    NTLM_WRONG_PASSWORD,
    FakeContext,
    ntlm_proof,
    ticket,
)
from tests.helpers import login

JAN = {"oid": "oid-jan", "email": "jan.peeters@example.com", "name": "Jan Peeters"}


# ---------------------------------------------------------------- helpers


def app_client(app: FastAPI) -> Generator[TestClient]:
    """The frontend-like client of `app`; `.close()` the generator to stop it."""
    yield from start_client(app)


def prepare(
    database: Database,
    *,
    name: str,
    username: str | None = None,
    email: str | None = None,
    role: str | None = None,
    node: str | None = "Coatings",
    status: UserStatus = UserStatus.ACTIVE,
) -> int:
    """A person an administrator prepared: no password, optionally with a role on a branch."""
    with database.session(write=True) as session:
        org = session.scalar(select(OrgNode.id).where(OrgNode.name == node)) if node else None
        user = User(
            kind=UserKind.PERSON,
            name=name,
            username=username,
            email=email,
            org_node_id=org,
            status=status,
        )
        session.add(user)
        session.flush()
        if role is not None:
            assert org is not None
            assignment = RoleAssignment(
                user_id=user.id,
                role_id=session.scalars(select(Role.id).where(Role.key == role)).one(),
            )
            assignment.scope = Scope.node(org)
            session.add(assignment)
        return user.id


def node_id(database: Database, name: str) -> int:
    with database.session() as session:
        return session.scalars(select(OrgNode.id).where(OrgNode.name == name)).one()


def edit_nodes(client: TestClient) -> list[int]:
    return client.get("/api/auth/me").json()["permissions"]["project.edit"]["node_ids"]


# ---------------------------------------------------------------- OpenID Connect


@pytest.fixture
def idp() -> FakeIdentityProvider:
    return FakeIdentityProvider()


def oidc_client(settings: Settings, idp: FakeIdentityProvider) -> Generator[TestClient]:
    providers = IdentityProviders(redirect={"entra": fake_oidc_provider(idp)})
    yield from start_client(create_app(settings, providers=providers))


@pytest.fixture
def client(
    sample_settings: Settings, sample_database: Database, idp: FakeIdentityProvider
) -> Iterator[TestClient]:
    del sample_database  # sample data is there before the app starts
    yield from oidc_client(sample_settings, idp)


@pytest.fixture
def jan(sample_database: Database) -> int:
    """Prepared by an administrator: no password, Project administrator on Coatings."""
    return prepare(
        sample_database,
        name="Jan Peeters",
        username="jan.peeters",
        email="Jan.Peeters@example.com",
        role="project_admin",
    )


def sign_in(
    client: TestClient,
    idp: FakeIdentityProvider,
    next_path: str = "/projects/4102",
    /,
    **claims: Any,
) -> Response:
    start = client.get(
        "/api/auth/sso/entra/start", params={"next": next_path}, follow_redirects=False
    )
    assert start.status_code == 303, start.text
    answer = idp.approve(start.headers["location"], **(claims or JAN))
    return client.get("/api/auth/sso/entra/callback", params=answer, follow_redirects=False)


def error_of(response: Response) -> str:
    location = response.headers["location"]
    assert "?sso_error=" in location, location
    return location


def test_the_login_options_list_the_provider(client: TestClient) -> None:
    login_options = client.get("/api/auth/me").json()["login"]
    assert login_options["providers"] == [{"name": "entra", "display_name": "Microsoft"}]
    assert login_options["password"] is True


def test_start_sends_the_browser_to_the_provider_with_pkce_and_nonce(client: TestClient) -> None:
    start = client.get("/api/auth/sso/entra/start", follow_redirects=False)
    assert start.status_code == 303
    location = start.headers["location"]
    assert location.startswith("https://idp.example.test/tenant/v2.0/authorize?")
    for part in (
        "response_type=code",
        "client_id=momato-tests",
        "code_challenge_method=S256",
        "nonce=",
        "state=",
    ):
        assert part in location
    assert "redirect_uri=http%3A%2F%2Ftestserver%2Fapi%2Fauth%2Fsso%2Fentra%2Fcallback" in location
    assert "momato_sso_state=" in start.headers["set-cookie"]
    assert "HttpOnly" in start.headers["set-cookie"]


def test_a_prepared_person_signs_in_with_the_prepared_rights(
    client: TestClient, idp: FakeIdentityProvider, jan: int, sample_database: Database
) -> None:
    done = sign_in(client, idp)
    assert done.status_code == 303
    assert done.headers["location"] == "/projects/4102"  # back where the sign-in started
    me = client.get("/api/auth/me").json()
    assert (me["username"], me["is_anonymous"], me["name"]) == ("jan.peeters", False, "Jan Peeters")
    assert edit_nodes(client) == [node_id(sample_database, "Coatings")]
    with sample_database.session() as session:
        links = session.execute(select(ExternalIdentity.provider, ExternalIdentity.subject)).all()
        logins = [
            e.details for e in session.scalars(select(AuditEntry)) if e.action == "auth.login"
        ]
    assert [(link.provider, link.subject) for link in links] == [("entra", "oid-jan")]
    assert logins == [{"method": "entra", "account": "linked"}]

    # The person is linked now; the next sign-in finds them by subject, whatever the email says.
    client.post("/api/auth/logout")
    again = sign_in(client, idp, oid="oid-jan", email="renamed@example.com")
    assert again.headers["location"] == "/projects/4102"
    assert client.get("/api/auth/me").json()["username"] == "jan.peeters"


def test_unknown_people_are_rejected_by_default(
    client: TestClient, idp: FakeIdentityProvider
) -> None:
    location = error_of(sign_in(client, idp, oid="oid-x", email="stranger@example.com"))
    assert "no%20account%20has%20been%20set%20up" in location
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_unknown_people_can_be_created_without_rights(
    sample_settings: Settings, sample_database: Database, idp: FakeIdentityProvider
) -> None:
    del sample_database
    settings = sample_settings.model_copy(update={"sso_unknown_users": UnknownUserPolicy.CREATE})
    clients = oidc_client(settings, idp)
    client = next(clients)
    sign_in(client, idp, oid="oid-new", email="new.person@example.com", name="New Person")
    me = client.get("/api/auth/me").json()
    assert (me["name"], me["is_anonymous"]) == ("New Person", False)
    assert me["username"] == "new.person.example.com"
    assert edit_nodes(client) == []  # only the defaults of everybody signed in
    assert client.get("/api/auth/me").json()["permissions"]["project.view"]["everywhere"] is True
    clients.close()


@pytest.mark.parametrize("status", [UserStatus.SUSPENDED, UserStatus.DEACTIVATED])
def test_suspended_and_deactivated_people_are_refused(
    client: TestClient,
    idp: FakeIdentityProvider,
    jan: int,
    sample_database: Database,
    status: UserStatus,
) -> None:
    del jan
    sign_in(client, idp)
    client.post("/api/auth/logout")
    with sample_database.session(write=True) as session:
        session.execute(update(User).where(User.username == "jan.peeters").values(status=status))
    assert f"this%20account%20is%20{status.value}" in error_of(sign_in(client, idp))
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_system_accounts_are_never_linked_by_email(
    client: TestClient, idp: FakeIdentityProvider, sample_database: Database
) -> None:
    with sample_database.session(write=True) as session:
        session.execute(
            update(User).where(User.username == "admin").values(email="boss@example.com")
        )
    error_of(sign_in(client, idp, oid="oid-evil", email="boss@example.com"))
    with sample_database.session() as session:
        assert session.scalar(select(ExternalIdentity.id)) is None


def test_the_callback_must_come_back_to_the_browser_that_started(
    sample_settings: Settings, sample_database: Database, idp: FakeIdentityProvider, jan: int
) -> None:
    del sample_database, jan
    attacker_clients, victim_clients = (
        oidc_client(sample_settings, idp),
        oidc_client(sample_settings, idp),
    )
    attacker, victim = next(attacker_clients), next(victim_clients)
    start = attacker.get("/api/auth/sso/entra/start", follow_redirects=False)
    answer = idp.approve(start.headers["location"], **JAN)
    # The attacker lures the victim to the callback with their own code and state (login CSRF).
    response = victim.get("/api/auth/sso/entra/callback", params=answer, follow_redirects=False)
    assert "not%20started%20in%20this%20browser" in error_of(response)
    assert victim.get("/api/auth/me").json()["is_anonymous"] is True
    attacker_clients.close()
    victim_clients.close()


def test_a_callback_cannot_be_replayed(
    client: TestClient, idp: FakeIdentityProvider, jan: int
) -> None:
    del jan
    start = client.get("/api/auth/sso/entra/start", follow_redirects=False)
    answer = idp.approve(start.headers["location"], **JAN)
    client.cookies.set("momato_sso_state", answer["state"])
    first = client.get("/api/auth/sso/entra/callback", params=answer, follow_redirects=False)
    assert first.headers["location"] == "/"
    client.post("/api/auth/logout")
    client.cookies.set("momato_sso_state", answer["state"])
    again = client.get("/api/auth/sso/entra/callback", params=answer, follow_redirects=False)
    assert "expired" in error_of(again)


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (lambda idp: setattr(idp, "token_audience", "someone-else"), "not%20valid"),
        (lambda idp: setattr(idp, "token_lifetime", -120), "not%20valid"),
        (lambda idp: setattr(idp, "nonce_override", "another-sign-in"), "nonce"),
        (lambda idp: setattr(idp, "sign_with", new_key()), "not%20valid"),
    ],
    ids=["wrong audience", "expired", "wrong nonce", "forged signature"],
)
def test_bad_tokens_are_refused(
    client: TestClient, idp: FakeIdentityProvider, jan: int, tamper: Any, message: str
) -> None:
    del jan
    tamper(idp)
    assert message in error_of(sign_in(client, idp))
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_key_rotation_is_followed(client: TestClient, idp: FakeIdentityProvider, jan: int) -> None:
    del jan
    sign_in(client, idp)
    client.post("/api/auth/logout")
    idp.rotate_keys()
    assert sign_in(client, idp).headers["location"] == "/projects/4102"


def test_the_provider_refusing_is_reported(client: TestClient) -> None:
    start = client.get("/api/auth/sso/entra/start", follow_redirects=False)
    state = start.headers["location"].split("state=")[1].split("&")[0]
    response = client.get(
        "/api/auth/sso/entra/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert "access_denied" in error_of(response)


def test_there_are_no_open_redirects(
    client: TestClient, idp: FakeIdentityProvider, jan: int
) -> None:
    del jan
    for evil in ("https://evil.example.com/", "//evil.example.com", "/\\evil"):
        assert sign_in(client, idp, evil).headers["location"] == "/"
        client.post("/api/auth/logout")


def test_an_unknown_provider_is_404(client: TestClient) -> None:
    assert client.get("/api/auth/sso/github/start", follow_redirects=False).status_code == 404


def test_without_a_configured_provider_no_sso_route_exists(
    sample_settings: Settings, sample_database: Database
) -> None:
    del sample_database
    clients = app_client(create_app(sample_settings))
    plain = next(clients)
    me = plain.get(
        "/api/auth/me", headers={"X-Remote-User": "CORP\\jdoe", "X-Fake-Sub": "oid-1"}
    ).json()
    assert me["is_anonymous"] is True
    assert me["login"]["providers"] == []
    assert me["login"]["windows"] is None
    paths = plain.get("/api/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/api/auth/sso")]
    assert "/api/auth/windows" not in paths
    assert plain.get("/api/auth/sso/entra/start").status_code in {404, 405}
    clients.close()


# ---------------------------------------------------------------- group mappings


def test_group_membership_grants_roles_while_it_lasts(
    client: TestClient, idp: FakeIdentityProvider, jan: int, sample_database: Database
) -> None:
    """[ADM-5] The provider says who is in which group at every sign-in."""
    del jan
    admin_clients = app_client(client.app)  # type: ignore[arg-type]  # a second browser
    admin = next(admin_clients)
    assert login(admin, "admin", TEST_ADMIN_PASSWORD).status_code == 200
    stl = node_id(sample_database, "STL")
    body = {
        "provider": "entra",
        "group_name": "g-quality",
        "role_key": "project_admin",
        "scope_kind": "node",
        "node_id": stl,
    }
    added = admin.post("/api/admin/group-mappings", json=body)
    assert added.status_code == 201
    assert added.json()[0]["scope_label"] == "STL"
    assert admin.post("/api/admin/group-mappings", json=body).status_code == 409
    assert (
        admin.post("/api/admin/group-mappings", json={**body, "role_key": "nope"}).status_code
        == 404
    )
    assert (
        admin.post(
            "/api/admin/group-mappings", json={**body, "scope_kind": "node", "node_id": None}
        ).status_code
        == 422
    )

    sign_in(client, idp, **(JAN | {"groups": ["g-quality", "g-other"]}))
    assert sorted(edit_nodes(client)) == sorted([node_id(sample_database, "Coatings"), stl])

    client.post("/api/auth/logout")
    sign_in(client, idp, **(JAN | {"groups": []}))  # left the group at the provider
    assert edit_nodes(client) == [node_id(sample_database, "Coatings")]

    listed = admin.get("/api/admin/group-mappings").json()
    assert [(m["group_name"], m["role_name"]) for m in listed] == [
        ("g-quality", "Project administrator")
    ]
    providers = admin.get("/api/admin/sso-providers").json()
    assert providers == [{"name": "entra", "display_name": "Microsoft", "kind": "redirect"}]
    after = admin.delete(f"/api/admin/group-mappings/{listed[0]['id']}")
    assert after.status_code == 200
    assert after.json() == []
    assert admin.delete("/api/admin/group-mappings/999999").status_code == 404
    entries = admin.get("/api/admin/audit", params={"action": "access.", "limit": 5}).json()
    assert [e["action"] for e in entries] == ["access.group_unmapped", "access.group_mapped"]
    # the person page shows how they signed in, and the groups last reported
    person = admin.get("/api/admin/people", params={"q": "jan.peeters"}).json()[0]
    assert [(i["provider"], i["groups"]) for i in person["identities"]] == [("entra", [])]
    admin_clients.close()


def test_group_mappings_need_users_manage(client: TestClient) -> None:
    assert client.get("/api/admin/group-mappings").status_code == 401
    assert client.get("/api/admin/sso-providers").status_code == 401


# ---------------------------------------------------------------- a trusted proxy header

HEADERS = {"X-Remote-User": "CORP\\JDoe", "X-Remote-Name": "John Doe"}


def header_client(settings: Settings, **overrides: object) -> Generator[TestClient]:
    settings = settings.model_copy(
        update={
            "trusted_header": "X-Remote-User",
            "trusted_header_name": "X-Remote-Name",
            "trusted_header_groups": "X-Remote-Groups",
            "trusted_proxies": "testclient",  # the TestClient's address
        }
        | overrides
    )
    yield from start_client(
        create_app(settings, providers=IdentityProviders.from_settings(settings))
    )


@pytest.fixture
def jdoe(sample_database: Database) -> int:
    """Prepared by login name (Windows logins usually carry no email)."""
    return prepare(
        sample_database, name="John Doe", username="jdoe", role="project_admin", node="Process"
    )


def test_the_proxy_identifies_a_prepared_person(
    sample_settings: Settings, jdoe: int, sample_database: Database
) -> None:
    del jdoe
    clients = header_client(sample_settings)
    client = next(clients)
    me = client.get("/api/auth/me", headers=HEADERS).json()
    assert me["username"] == "jdoe"
    assert me["signed_in_by"] == "Windows sign-in"  # so the page offers no "Log out"
    assert me["permissions"]["project.edit"]["node_ids"] == [node_id(sample_database, "Process")]
    # Without the header (the proxy did not authenticate) the visitor is anonymous.
    assert client.get("/api/auth/me").json()["is_anonymous"] is True
    clients.close()


def test_headers_from_anyone_but_the_proxy_are_ignored(
    sample_settings: Settings, jdoe: int
) -> None:
    del jdoe
    clients = header_client(sample_settings, trusted_proxies="10.0.0.5")
    client = next(clients)
    assert client.get("/api/auth/me", headers=HEADERS).json()["is_anonymous"] is True
    clients.close()


def test_the_proxy_may_forward_the_client_address(sample_settings: Settings, jdoe: int) -> None:
    """IIS ARR adds X-Forwarded-For (with the client's port); the proxy still vouches."""
    del jdoe
    clients = header_client(sample_settings)
    client = next(clients)
    forwarded = HEADERS | {"X-Forwarded-For": "203.0.113.5:51234", "X-Forwarded-Proto": "https"}
    assert client.get("/api/auth/me", headers=forwarded).json()["username"] == "jdoe"
    clients.close()


def test_group_headers_feed_group_mappings(
    sample_settings: Settings, jdoe: int, sample_database: Database
) -> None:
    del jdoe
    with sample_database.session(write=True) as session:
        mapping = GroupRoleMapping(
            provider="proxy",
            group_name="STL-Maintenance",
            role_id=session.scalars(select(Role.id).where(Role.key == "project_admin")).one(),
        )
        mapping.scope = Scope.node(node_id(sample_database, "Maintenance"))
        session.add(mapping)
    clients = header_client(sample_settings)
    client = next(clients)
    me = client.get(
        "/api/auth/me", headers=HEADERS | {"X-Remote-Groups": "STL-Maintenance, Everyone"}
    ).json()
    assert sorted(me["permissions"]["project.edit"]["node_ids"]) == sorted(
        [node_id(sample_database, "Process"), node_id(sample_database, "Maintenance")]
    )
    clients.close()


def test_the_domain_can_be_kept_in_the_username(
    sample_settings: Settings, sample_database: Database
) -> None:
    prepare(sample_database, name="Corp Doe", username="corp\\jdoe", node=None)
    clients = header_client(sample_settings, trusted_header_strip_domain=False)
    client = next(clients)
    assert client.get("/api/auth/me", headers=HEADERS).json()["username"] == "corp\\jdoe"
    clients.close()


class FakeHeaderProvider:
    """A stand-in ambient provider: trusts `X-Fake-Sub` and `X-Fake-Email`."""

    name = "fake"
    display_name = "Fake SSO"

    def identify(self, headers: Mapping[str, str], proxy: str | None) -> Identity | None:
        subject = headers.get("x-fake-sub")
        if not subject:
            return None
        return Identity(self.name, subject, email=headers.get("x-fake-email"), display_name=subject)


def test_an_ambient_unknown_person_is_refused_with_401(
    sample_settings: Settings, sample_database: Database
) -> None:
    del sample_database
    clients = app_client(
        create_app(sample_settings, providers=IdentityProviders(ambient=[FakeHeaderProvider()]))
    )
    client = next(clients)
    response = client.get(
        "/api/auth/me", headers={"X-Fake-Sub": "oid-9", "X-Fake-Email": "x@y.org"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"
    clients.close()


# ---------------------------------------------------------------- Windows sign-in (Negotiate)

JDOE = "CORP\\JDoe"
URL = "/api/auth/windows"


def windows_client(
    settings: Settings, provider: NegotiateProvider | None = None
) -> Generator[TestClient]:
    provider = provider or NegotiateProvider(new_context=FakeContext)
    yield from start_client(create_app(settings, providers=IdentityProviders(negotiate=provider)))


def negotiate(client: TestClient, token: bytes) -> Response:
    """What a browser sends in answer to a challenge."""
    header = f"Negotiate {base64.b64encode(token).decode()}"
    return client.post(URL, headers={"Authorization": header})


def answer(response: Response) -> bytes:
    """The token in the response's `WWW-Authenticate: Negotiate <token>`."""
    scheme, _, value = response.headers["www-authenticate"].partition(" ")
    assert scheme == "Negotiate"
    return base64.b64decode(value)


@pytest.fixture
def windows(sample_settings: Settings, sample_database: Database) -> Iterator[TestClient]:
    prepare(sample_database, name="John Doe", username="jdoe", role="project_admin", node="Process")
    yield from windows_client(sample_settings)


def test_windows_sign_in_is_off_unless_configured(client: TestClient) -> None:
    assert client.post(URL).status_code in {404, 405}
    assert client.get("/api/auth/me").json()["login"]["windows"] is None


def test_the_page_is_told_to_try_by_itself(windows: TestClient) -> None:
    assert windows.get("/api/auth/me").json()["login"]["windows"] == {"automatic": True}


def test_the_page_can_be_told_to_wait_for_a_click(
    sample_settings: Settings, sample_database: Database
) -> None:
    del sample_database
    clients = windows_client(
        sample_settings, NegotiateProvider(automatic=False, new_context=FakeContext)
    )
    client = next(clients)
    assert client.get("/api/auth/me").json()["login"]["windows"] == {"automatic": False}
    clients.close()


@pytest.mark.parametrize("authorization", [None, "Basic amRvZTpwdw==", "Negotiate", "Negotiate ?"])
def test_a_request_without_a_token_is_challenged(
    windows: TestClient, authorization: str | None
) -> None:
    response = windows.post(URL, headers={"Authorization": authorization} if authorization else {})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Negotiate"
    assert response.json()["error"] == "windows_sign_in_required"
    assert "momato_session" not in response.cookies


def test_a_kerberos_ticket_signs_in_with_one_request(
    windows: TestClient, sample_database: Database
) -> None:
    response = negotiate(windows, ticket(JDOE))
    assert response.status_code == 200, response.text
    assert answer(response) == LAST_WORD  # the browser checks the server in turn
    assert response.json()["username"] == "jdoe"
    # From here on it is an ordinary session: the cookie identifies the person...
    me = windows.get("/api/auth/me").json()
    assert (me["username"], me["is_anonymous"], me["signed_in_by"]) == ("jdoe", False, None)
    assert me["permissions"]["project.edit"]["node_ids"] == [node_id(sample_database, "Process")]
    # ...who can log out, e.g. to use the built-in admin account.
    assert windows.post("/api/auth/logout").status_code == 204
    assert windows.get("/api/auth/me").json()["is_anonymous"] is True


def test_ntlm_signs_in_with_two_requests(windows: TestClient) -> None:
    first = negotiate(windows, NTLM_HELLO)
    assert first.status_code == 401
    assert answer(first) == NTLM_CHALLENGE
    second = negotiate(windows, ntlm_proof(JDOE))
    assert second.status_code == 200, second.text
    assert "www-authenticate" not in second.headers
    assert windows.get("/api/auth/me").json()["username"] == "jdoe"


def test_a_refused_token_is_challenged_again(windows: TestClient) -> None:
    """So the browser can ask for a user name and password, as with any Windows-protected site."""
    negotiate(windows, NTLM_HELLO)
    response = negotiate(windows, NTLM_WRONG_PASSWORD)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Negotiate"
    assert response.json()["error"] == "windows_sign_in_required"
    assert windows.get("/api/auth/me").json()["is_anonymous"] is True


def test_someone_without_an_account_is_refused_without_a_new_challenge(
    windows: TestClient,
) -> None:
    response = negotiate(windows, ticket("CORP\\Stranger"))
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"
    assert "no account has been set up for you" in response.json()["message"]
    assert "www-authenticate" not in response.headers  # asking again would not help
    assert windows.get("/api/auth/me").json()["is_anonymous"] is True


def test_unknown_people_can_get_an_account_without_rights(
    sample_settings: Settings, sample_database: Database
) -> None:
    del sample_database
    clients = windows_client(
        sample_settings.model_copy(update={"sso_unknown_users": UnknownUserPolicy.CREATE})
    )
    client = next(clients)
    me = negotiate(client, ticket("CORP\\Stranger")).json()
    assert (me["username"], me["name"], me["is_anonymous"]) == ("stranger", "Stranger", False)
    assert me["permissions"]["project.edit"] == {"everywhere": False, "node_ids": []}
    clients.close()


def test_a_suspended_account_is_refused(windows: TestClient, sample_database: Database) -> None:
    prepare(sample_database, name="Anna Away", username="anna", status=UserStatus.SUSPENDED)
    response = negotiate(windows, ticket("CORP\\Anna"))
    assert response.status_code == 403
    assert response.json()["message"] == "this account is suspended"


def test_signing_in_needs_the_csrf_header(windows: TestClient) -> None:
    del windows.headers[CSRF_HEADER]
    response = negotiate(windows, ticket(JDOE))
    assert (response.status_code, response.json()["error"]) == (403, "csrf_failed")
