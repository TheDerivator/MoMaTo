# Accounts, access rights and sign-in

How MoMaTo decides who someone is and what they may do. Code: `momato/domain/access.py` and
`momato/domain/orgtree.py` (the rules, pure), `momato/identity/` (database-backed parts and the
policy), `momato/services/auth.py` and `momato/services/access.py` (use cases),
`momato/api/routers/auth.py` (endpoints). The requirements are AUTH-1 to AUTH-5 and §6 of
[`REQUIREMENTS.md`](REQUIREMENTS.md).

## Concepts

| Concept | Meaning |
|---|---|
| **Person** | One record per person, who may or may not be able to sign in (D-012). Persons are the people of pickers, planning and timesheets. |
| **System account** | The built-in `admin` (break-glass administrator) and `anonymous` (every visitor who is not signed in). They are never people: no timesheet, not in pickers or planning. |
| **Permission** | `project.view`, `project.edit`, `project.comment`, `project.delete`, `plan.manage`, `hours.view` apply per org node and its whole branch. `org.manage` and `users.manage` apply only when granted globally. |
| **Role** | A named set of permissions. Built-in (re-synced from code at every start): *Viewer*, *Project administrator*, *Hours viewer*, *Administrator*. Custom roles are possible. |
| **Assignment** | A person holds a role at a **scope**: global, one org node (its branch), or *own department*. |
| **Own department** | Resolved at each request to the nearest *department*-flagged node on the path from the person's node up to the root (D-006); nothing when they have none. It moves with the person and with the flags. |
| **Default grants** | Roles every signed-in person holds, and roles every visitor holds (a floor for everyone). Administrators change them like assignments (D-013). |

### Permissions and built-in roles

| Permission | Scope | Viewer | Project administrator | Hours viewer | Administrator |
|---|---|:-:|:-:|:-:|:-:|
| `project.view` | branch of the project's node | ✔ | ✔ | | ✔ |
| `project.edit` | same | | ✔ | | ✔ |
| `project.comment` | same | | ✔ | | ✔ |
| `project.delete` | same | | | | ✔ |
| `plan.manage` | branch of the plan's owner | | ✔ | | ✔ |
| `hours.view` | branch of the person's node | | | ✔ | ✔ |
| `org.manage` | global | | | | ✔ |
| `users.manage` | global | | | | ✔ |

Defaults of a fresh installation: every signed-in person is *Viewer* globally and *Hours viewer* on
their own department; visitors hold nothing, so MoMaTo requires a sign-in.

## Rules

1. A scoped permission applies to an object when it is held globally or on any node on the path
   from the object's node up to the root. A global permission counts only when assigned
   globally: an *Administrator* assigned to one branch has full project rights there and no user
   or organisation management.
2. The *own department* scope is resolved per request (see above).
3. Default grants hold for every signed-in person; the anonymous visitor's grants are a floor for
   everyone, so signing in never shows less.
4. A project's **coordinator** may view, edit and comment on it, and its **members** may view and
   comment (D-014), whatever their assignments. Everyone sees their own booked time.
5. Lists and counts only contain what the caller may see; an invisible project answers 404, like a
   missing one. Routers never decide access: one policy object (`identity/policy.py`) answers
   `can(...)` and builds the query filters; services call it.
6. A suspended or deactivated person loses access at their next request (sessions are
   server-side and checked on every request).
7. A person flagged *must change password* (a generated or administrator-set password) can do
   nothing but change it.
8. The server enforces every rule; `GET /api/auth/me` tells the frontend where each permission
   applies so it can hide controls, nothing more.
9. At least one active administrator always remains (the lockout guard): removing the last global
   `users.manage` assignment, or suspending its holder, is refused.

## Password sign-in

- Passwords are hashed with argon2id and upgraded at login when the parameters change; minimum
  length 10.
- Sessions: a random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` over HTTPS,
  or forced with `MOMATO_COOKIE_SECURE`); the database stores only its SHA-256 hash. Lifetime
  `MOMATO_SESSION_LIFETIME_HOURS` (default 14 days). Logout, suspension and password changes end
  sessions immediately; a password change ends all *other* sessions of that person.
- Throttling: after `MOMATO_LOGIN_MAX_FAILURES_PER_USER` (5) failures since the last success, or
  `MOMATO_LOGIN_MAX_FAILURES_PER_IP` (50) from one address, within `MOMATO_LOGIN_THROTTLE_MINUTES`
  (15), logins are refused with HTTP 429 and `Retry-After`. Behind a reverse proxy, list it in
  `MOMATO_TRUSTED_PROXIES`: only then are `X-Forwarded-For` and `-Proto` believed.
- Errors never reveal whether a username exists, and unknown usernames take as long as known ones.
- CSRF: every state-changing API request must carry `X-CSRF-Token` equal to the `momato_csrf`
  cookie (double submit), on top of `SameSite` cookies. Requests with an API token are exempt
  (they are judged by the token alone).
- The first `admin` password comes from `MOMATO_INITIAL_ADMIN_PASSWORD`, or is generated, written
  once to the server log (and printed by `python -m momato seed`), and must be changed at first
  login. `python -m momato create-admin [--password PW]` creates or repairs the account: active,
  *Administrator* everywhere, with a password (generated, to be changed, when none is given).
- `python -m momato seed --sample --demo-password PW` lets every sample person sign in as
  `firstname.lastname` (demos only).

## Audit log

Sign-ins, password changes, role grants and revocations, default grant changes and status changes
are recorded in `audit_log` in the same transaction as the change (AUTH-5). The viewer is
Administration › Audit log (M10).

## API tokens (AI agents and scripts)

`Authorization: Bearer mm_…`, created on the Profile page (read only or read and write, expiring
after 7 / 30 / 90 / 365 days or never). Only a hash is stored and the secret is shown once. A token
acts as its owner with the owner's current rights narrowed by its scope: *read* holds the view
permissions and every request that is not GET, HEAD or OPTIONS is refused; *write* holds
everything except `org.manage` and `users.manage`. A scope narrows the implicit coordinator and
member rights too. A request with a Bearer header is judged by that token alone (a bad one is
401, never the cookie's person), needs no CSRF header, and is refused when its owner is suspended
or deactivated. Tokens are created and revoked in the app itself, never through a token; people
with `users.manage` can list and revoke anyone's. What a token wrote shows "via <token name>" in
the logbook, in remarks and on time entries. Code: `identity/api_tokens.py`,
`services/tokens.py`, `api/routers/tokens.py`; the guide for agents is `GET /api/agent-guide`
(TOK-1 – TOK-4, D-059).

## SSO (external identity providers)

SSO is **off unless configured**. With no provider configured only built-in sign-in exists, the
SSO routes are not mounted and identity headers are ignored. Three providers exist and can be
enabled together:

| Provider | Shape | Name (stored with linked people) | Enabled by |
|---|---|---|---|
| OpenID Connect, e.g. **Microsoft Entra ID** | *redirect*: the login dialog shows "Sign in with Microsoft" | `MOMATO_OIDC_NAME` (default `entra`) | `MOMATO_OIDC_ISSUER` + `MOMATO_OIDC_CLIENT_ID` |
| **Windows sign-in** by MoMaTo itself | *negotiate*: the browser proves the Windows login to the app (Kerberos or NTLM), once per session | `windows` | `MOMATO_WINDOWS_AUTH` |
| **Trusted header** from an authenticating proxy | *ambient*: every request through the proxy carries the person | `proxy` | `MOMATO_TRUSTED_HEADER` |

Code: `momato/identity/providers/` (`oidc.py`, `negotiate.py`, `header.py`),
`momato/identity/provisioning.py`, `momato/services/sso.py`,
`momato/api/routers/` (`sso.py`, `windows.py`).

### How an SSO sign-in becomes a person

A provider hands over an `ExternalIdentity(provider, subject, email, display_name, groups, username)`.
`provisioning.py` then:

1. uses the person already linked to `(provider, subject)`, if any;
2. otherwise a person with the same **email**, prepared in advance by an administrator (with
   their rights): the identity is linked, so the prepared rights apply from the first request;
3. otherwise (Windows sign-in has no email) a person whose **username** equals the provider's
   login name (`CORP\jdoe` becomes `jdoe`), linked the same way;
4. otherwise `MOMATO_SSO_UNKNOWN_USERS`: `reject` (default, invite-only: "no account has been
   set up for you") or `create` (a new person without roles of their own).

System accounts (`admin`, `anonymous`) are never linked by email or username, and a person
already linked to another identity of the same provider is not taken over. Suspended and
deactivated people are refused whatever the provider says. Password sign-in keeps working next to
SSO; the built-in `admin` stays the break-glass account. Links and created people are in the audit
log. **To prepare someone:** Administration › People › New person (place, job title), then their
page › Sign-in: the work email (Entra ID: the UPN) and/or the Windows login name as username; no
password; then their roles under Access.

### Group mappings

Administration › Single sign-on gives everyone in an identity-provider group a role at a scope
("members of `STL-Maintenance` are *Project administrator* on STL › Maintenance"). The groups a
provider reports are stored with the link and refreshed at every sign-in (OIDC) or whenever the
proxy reports different ones (header), so rights follow group membership. They come on top of a
person's own assignments and never take anything away. Names are compared exactly, as the
provider sends them. Entra ID sends group **object ids**; tokens carry at most 200 groups
(beyond that Entra ID leaves the claim out), so use *Groups assigned to the application*. Windows
sign-in reports no groups.

### Microsoft Entra ID (OpenID Connect)

1. App registrations › New registration: single tenant. Redirect URI (platform *Web*):
   `https://<host>/<base path>/api/auth/sso/entra/callback` (`entra` is `MOMATO_OIDC_NAME`).
2. Certificates & secrets: a client secret (note its expiry: sign-in stops when it does).
3. Optional, for group mappings: Token configuration › Add groups claim.
4. Settings:

   ```ini
   MOMATO_OIDC_ISSUER=https://login.microsoftonline.com/<tenant id>/v2.0
   MOMATO_OIDC_CLIENT_ID=<application (client) id>
   MOMATO_OIDC_CLIENT_SECRET=<secret value>
   MOMATO_OIDC_SUBJECT_CLAIM=oid
   MOMATO_PUBLIC_URL=https://momato.corp.example/momato/
   ```

   Optional: `MOMATO_OIDC_DISPLAY_NAME` (the button, default "Microsoft"), `MOMATO_OIDC_SCOPES`,
   `MOMATO_OIDC_EMAIL_CLAIMS` (the first present is the email; default
   `email,preferred_username,upn`), `MOMATO_OIDC_GROUPS_CLAIM`.

`MOMATO_PUBLIC_URL` is the address people type; the redirect URI is built from it and must match
the registration exactly. Use a tenant-specific issuer, never `common` or `organizations`.
**What the app checks:** authorization code flow with PKCE; a random *state* (stored hashed,
single use, 10 minutes, bound to the browser by the `momato_sso_state` cookie) and a *nonce* that
must come back inside the ID token; the ID token's signature against the provider's published keys
(refetched once for an unknown key id), algorithm (RS/PS/ES only), issuer, audience and expiry.
After sign-in the browser returns to the page it started from (only paths on this site). Failures
return to MoMaTo with a message.

### Windows sign-in (Negotiate)

MoMaTo runs on a Windows server that browsers reach **directly**:

```ini
MOMATO_WINDOWS_AUTH=true
MOMATO_HOST=0.0.0.0
```

Optional: `MOMATO_WINDOWS_AUTH_AUTOMATIC=false` (the login dialog offers "Sign in with Windows"
instead of trying by itself), `MOMATO_WINDOWS_AUTH_STRIP_DOMAIN=false` (people are prepared as
`corp\jdoe`), `MOMATO_TLS_CERTFILE` + `MOMATO_TLS_KEYFILE` (HTTPS by the app itself).

The page posts to `/api/auth/windows` (mounted only when switched on); the answer is `401` with
`WWW-Authenticate: Negotiate`, the browser (if the site is in its intranet zone) repeats with a
token, and Windows (SSPI through pyspnego) verifies it: Kerberos in one request, NTLM in two on the
**same connection** (a half-finished handshake is remembered per connection for 30 seconds, in
memory). The result goes through provisioning and MoMaTo starts an **ordinary session**: only
that endpoint challenges; "Log out" and the built-in admin keep working, and after a logout the
page does not sign in by itself again in that tab. A reverse proxy that shares connections among
clients breaks NTLM (Kerberos is unaffected). `serve` raises Uvicorn's header limit to 128 kB for
Kerberos tickets. For Kerberos the service must run as an identity the domain knows under the
name in the address (`setspn -S HTTP/<server> <account>` for a domain service account).

### Trusted header (an authenticating proxy)

A reverse proxy authenticates people and passes the login name in a request header. Only do this
when MoMaTo is reachable **exclusively** through that proxy, which sets the header on every
request, overwriting what a client sent. IIS cannot fill the header with its own modules (URL
Rewrite runs before IIS authenticates); use Windows sign-in above for Windows accounts.

```ini
MOMATO_TRUSTED_HEADER=X-Remote-User
MOMATO_TRUSTED_PROXIES=127.0.0.1,::1
```

Optional: `MOMATO_TRUSTED_HEADER_EMAIL`, `_NAME`, `_GROUPS` (comma-separated), and
`MOMATO_TRUSTED_HEADER_STRIP_DOMAIN=false`. The header is believed only on requests that come
through one of `MOMATO_TRUSTED_PROXIES` (from anywhere else it is ignored and a warning is
logged once). Such visitors are signed in on every request, so the page offers no "Log out". To
use the built-in `admin`, open MoMaTo on the server itself (`http://127.0.0.1:8000/`): requests
that bypass the proxy carry no identity header.

### Reverse proxies and client addresses

`MOMATO_TRUSTED_PROXIES` lists the proxies whose `X-Forwarded-For` and `-Proto` are believed (the
client address for login throttling and audit, the scheme for `Secure` cookies and redirect
URIs). The app reads them itself (`momato/api/client.py`), so Uvicorn's `--proxy-headers` must be
off: `python -m momato serve` does that.

### Security notes

- `subject` is the provider's stable, non-reassignable id (Entra ID: `oid`; Windows sign-in and
  the header: the full `DOMAIN\login`), never an email or a name.
- Windows sign-in links a prepared person by **username**: whoever holds that Windows login gets
  that person (system accounts excepted). With several domains that reuse login names, keep the
  domain (`MOMATO_WINDOWS_AUTH_STRIP_DOMAIN=false`).
- NTLM can be relayed by someone who lures a person to a server of theirs, and the session cookie
  travels unencrypted over plain HTTP: use HTTPS beyond an experiment.
- Emails link prepared people, so they must come from a directory your organisation manages. After
  the first link the person is found by `subject` only.
- Anything that can send requests from a trusted proxy address (with the default setting: any
  program on the server itself) can claim any identity through the trusted header.
- Group mappings are powerful: whoever can add people to a mapped group grants them rights here.
