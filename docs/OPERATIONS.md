# Running MoMaTo

How to install, run, back up and upgrade MoMaTo on the two targets: a **Linux demo server**
(built-in accounts only, internet-facing) and a **corporate Windows server** (built-in accounts,
optionally Microsoft Entra ID or Windows sign-in, SQLite now and MS SQL later). Single sign-on
configuration itself is in [`AUTH.md`](AUTH.md).

> The commands and configuration files below follow each product's documentation. The Python
> side (serve, migrations, proxy headers, sign-in, the Windows handshake) is covered by the test
> suite, but the systemd, Caddy/nginx, WinSW and IIS parts have not been tried on a real server
> yet, and nor has MS SQL (there was no SQL Server to test against). Please report what needed
> changing.

## The shape of a deployment

```
browser ──HTTPS──> reverse proxy (Caddy / nginx / IIS) ──HTTP──> MoMaTo on 127.0.0.1:8000
                   TLS, HSTS, upload size limit                  one process: python -m momato serve
                                                                 data folder: database + uploads
```

- **One process.** `python -m momato serve` runs Uvicorn with one worker, which is plenty for an
  organisation of hundreds (the scale budgets of REQUIREMENTS 8.5 are measured that way). SQLite
  serialises writes anyway.
- **Only the proxy reaches the app.** MoMaTo listens on `127.0.0.1` (the default `MOMATO_HOST`).
  The proxy is listed in `MOMATO_TRUSTED_PROXIES` (default `127.0.0.1,::1`), so the client's
  address and scheme come from its `X-Forwarded-*` headers.
- **The exception: Windows sign-in.** There, browsers reach MoMaTo directly
  (`MOMATO_HOST=0.0.0.0`, no proxy) and it can serve HTTPS itself: see
  [*Windows sign-in, without IIS*](#windows-sign-in-without-iis).
- **One data folder** (`MOMATO_DATA_DIR`): `momato.sqlite3` (plus `-wal`/`-shm` files while
  running) and `uploads/` (remark images). Only the service account needs access to it: it holds
  password and session hashes.
- **Settings** come from environment variables, or from a `.env` file in the app folder (see
  [`.env.example`](../.env.example)). Environment variables win.
- **Migrations run at start** (`MOMATO_AUTO_MIGRATE=true`), and so do the built-in roles and
  accounts. On the first start without `MOMATO_INITIAL_ADMIN_PASSWORD`, a generated `admin`
  password is written once to the log; it must be changed at first login.
- **The profile** (`MOMATO_PROFILE`, default `default`) fixes the detail fields, time categories,
  task template and a few numbers of the deployment; it is a file in `momato/profiles/` and a
  broken one stops the server with a clear message.

Settings that matter in production:

| Setting | Why |
|---|---|
| `MOMATO_ENVIRONMENT=production` | Serves the page from memory (development re-reads it per request). |
| `MOMATO_DATA_DIR` | Outside the app folder, e.g. `/var/lib/momato` or `C:\ProgramData\MoMaTo`. |
| `MOMATO_INITIAL_ADMIN_PASSWORD` | Optional: choose the first `admin` password instead of reading it from the log. |
| `MOMATO_BASE_PATH` | When published under a prefix, e.g. `/momato/` (the proxy strips it). |
| `MOMATO_PUBLIC_URL` | The address people type: SSO redirect URIs and the agent guide use it. |
| `MOMATO_TRUSTED_PROXIES` | If the proxy runs on another machine: its address. |
| `MOMATO_TLS_CERTFILE`, `MOMATO_TLS_KEYFILE` | Only without a proxy: HTTPS by the app itself (PEM files). |
| `MOMATO_COOKIE_SECURE` | Leave unset: `Secure` follows the request's scheme (behind the proxy: `X-Forwarded-Proto`). |

Do not start Uvicorn with its own `--proxy-headers` (its default when you run `uvicorn app:app`):
the app handles forwarded headers itself. `python -m momato serve` gets this right; with
`uvicorn app:app`, add `--no-proxy-headers`.

## Linux demo server

Built-in accounts only: leave every `MOMATO_OIDC_*` and `MOMATO_TRUSTED_HEADER` unset.

### Install

```sh
sudo useradd --system --home /var/lib/momato --shell /usr/sbin/nologin momato
sudo mkdir -p /opt/momato /var/lib/momato /etc/momato
sudo chown momato:momato /var/lib/momato && sudo chmod 700 /var/lib/momato
# Put the code in /opt/momato (git clone or copy), then, with uv installed:
cd /opt/momato
sudo env UV_PYTHON_INSTALL_DIR=/opt/momato/.python uv sync --frozen --no-dev
```

`UV_PYTHON_INSTALL_DIR` keeps the Python that uv downloads inside the app folder; by default it
would land in root's home, where the service account cannot run it.

`/etc/momato/momato.env` (readable by root and the service only, `chmod 640`, group `momato`):

```ini
MOMATO_ENVIRONMENT=production
MOMATO_DATA_DIR=/var/lib/momato
MOMATO_INITIAL_ADMIN_PASSWORD=<a long password>
```

Demo content (optional): 70 people in ten departments, 200 projects with tasks, planned days,
remarks and logbooks, twelve action plans and two years of booked time, every person able to sign
in as `firstname.lastname`. Its dates move so that the sample's "today" is the day you seed;
seeding only fills an empty database:

```sh
sudo -u momato sh -c 'set -a; . /etc/momato/momato.env; exec /opt/momato/.venv/bin/python -m momato seed --sample --demo-password "<demo password>"'
```

### systemd

`/etc/systemd/system/momato.service`:

```ini
[Unit]
Description=MoMaTo
After=network.target

[Service]
User=momato
Group=momato
WorkingDirectory=/opt/momato
EnvironmentFile=/etc/momato/momato.env
ExecStart=/opt/momato/.venv/bin/python -m momato serve
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/momato

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload && sudo systemctl enable --now momato
journalctl -u momato -f        # the log, including a generated admin password
```

### Reverse proxy with TLS

Caddy (gets and renews the certificate itself; sends `X-Forwarded-For` and `-Proto` by default):

```
momato.example.org {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 12MB
    }
    header Strict-Transport-Security "max-age=31536000"
}
```

Or nginx:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name momato.example.org;
    ssl_certificate     /etc/letsencrypt/live/momato.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/momato.example.org/privkey.pem;
    client_max_body_size 12m;      # remark images are up to 10 MB
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Responses over 1 kB are compressed by the app; the proxy need not do it.

### Before opening it to the internet

- Log in as `admin` and change the password (or set it through the env file, above).
- Everyone signed in sees everything (the *Viewer* default grant) and visitors see nothing:
  Administration › Default access changes both.
- Demo passwords are shared secrets: use them on the demo only.
- Failed logins are throttled per account and per address (AUTH.md); the addresses are real ones
  because the proxy is trusted.

## Windows server

### Install

1. Install [uv](https://docs.astral.sh/uv/) for all users, and put the code in e.g.
   `C:\MoMaTo\app`.
2. In PowerShell: `cd C:\MoMaTo\app`, `$env:UV_PYTHON_INSTALL_DIR = "C:\MoMaTo\python"`,
   `$env:UV_LINK_MODE = "copy"`, then `uv sync --frozen --no-dev` (add `--extra mssql` for MS
   SQL). The install directory keeps the Python that uv downloads out of your own profile, where
   the service could not run it. Copying (instead of uv's default hard links into its cache in
   your profile) gives the packages the app folder's permissions. Set both again before every
   later `uv sync`.
3. Create `C:\ProgramData\MoMaTo` and give the service account (below) *Modify* rights on it and
   *Read & execute* on `C:\MoMaTo`.
4. `C:\MoMaTo\app\.env`:

   ```ini
   MOMATO_ENVIRONMENT=production
   MOMATO_DATA_DIR=C:\ProgramData\MoMaTo
   MOMATO_INITIAL_ADMIN_PASSWORD=<a long password>
   MOMATO_PUBLIC_URL=https://momato.corp.example/
   ```

### Windows service (WinSW)

[WinSW](https://github.com/winsw/winsw) is a small, MIT-licensed service wrapper. Copy
`WinSW-x64.exe` to `C:\MoMaTo\MoMaTo.exe` and put `C:\MoMaTo\MoMaTo.xml` next to it:

```xml
<service>
  <id>MoMaTo</id>
  <name>MoMaTo</name>
  <description>Project management (python -m momato serve)</description>
  <executable>C:\MoMaTo\app\.venv\Scripts\python.exe</executable>
  <arguments>-m momato serve</arguments>
  <workingdirectory>C:\MoMaTo\app</workingdirectory>
  <onfailure action="restart" delay="10 sec" />
  <log mode="roll-by-size" />
</service>
```

```bat
C:\MoMaTo\MoMaTo.exe install
C:\MoMaTo\MoMaTo.exe start
```

Run the service under a dedicated account with only the rights listed above (*Services ›
MoMaTo › Log On*). WinSW writes the service's output to log files next to `MoMaTo.exe`; a
generated `admin` password would appear there (Uvicorn logs to the error stream).

### IIS as reverse proxy

Install the IIS modules *URL Rewrite* and *Application Request Routing* (ARR). In IIS Manager:
server node › *Application Request Routing Cache* › *Server Proxy Settings* › *Enable proxy*. Keep
"Preserve client IP in the following header: X-Forwarded-For" on. In *URL Rewrite › View Server
Variables*, allow `HTTP_X_FORWARDED_PROTO`.

The site (HTTPS binding with the corporate certificate) gets this `web.config`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="MoMaTo" stopProcessing="true">
          <match url="(.*)" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
          </serverVariables>
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="12582912" />
      </requestFiltering>
    </security>
    <httpProtocol>
      <customHeaders>
        <add name="Strict-Transport-Security" value="max-age=31536000" />
      </customHeaders>
    </httpProtocol>
  </system.webServer>
</configuration>
```

Under a prefix (`https://intranet.corp.example/momato/`): match `^momato/(.*)`, keep the action,
and set `MOMATO_BASE_PATH=/momato/` and `MOMATO_PUBLIC_URL=https://intranet.corp.example/momato/`.

Microsoft Entra ID sign-in: see [`AUTH.md`](AUTH.md).

### Windows sign-in, without IIS

People are signed in as their Windows account (Kerberos or NTLM) by MoMaTo itself. IIS cannot
pass the Windows user on to MoMaTo with its own modules (URL Rewrite runs before IIS
authenticates: [`AUTH.md`](AUTH.md#trusted-header-an-authenticating-proxy)), so in this setup no
proxy is in front.

```
browser ──HTTP or HTTPS──> MoMaTo (the Windows service above) on 0.0.0.0:<port>
                           Negotiate handshake on /api/auth/windows, checked by Windows (SSPI)
```

```ini
MOMATO_HOST=0.0.0.0
MOMATO_PORT=8080
MOMATO_WINDOWS_AUTH=true
# HTTPS (PEM files; the certificate first, then its intermediates; the key without a password):
MOMATO_TLS_CERTFILE=C:\MoMaTo\tls\cert.pem
MOMATO_TLS_KEYFILE=C:\MoMaTo\tls\key.pem
```

- Run the service as its own account (`sc.exe config MoMaTo obj= "NT SERVICE\MoMaTo"`): it acts
  as the computer on the network, which Kerberos needs, and no SPN has to be registered.
- MoMaTo needs a port of its own (no URL prefix, no sharing of 80/443 with IIS sites), opened in
  the firewall.
- The browsers must treat the site as intranet (Windows' intranet zone, or Chromium's
  `AuthServerAllowlist` policy), or they will not answer the Negotiate challenge.
- No proxy means no HSTS header and no upload size limit in front; the app enforces its own
  limits.
- Prepare each person under Administration › People with their Windows login name as username
  (see AUTH.md); the first sign-in links them.

### MS SQL (later)

1. Install *Microsoft ODBC Driver 18 for SQL Server* and run `uv sync --frozen --no-dev --extra mssql`.
2. The DBA creates an empty database and a login that may create tables in it
   (`db_ddladmin`, `db_datareader`, `db_datawriter`): the schema is created by the migrations at
   the first start. Any case-insensitive default collation works.
3. `MOMATO_DATABASE_URL`, for example (URL-encode special characters in the password):

   ```ini
   # SQL login
   MOMATO_DATABASE_URL=mssql+pyodbc://momato:<password>@sqlserver.corp.example/MoMaTo?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes
   # or the service account's Windows login
   MOMATO_DATABASE_URL=mssql+pyodbc://@sqlserver.corp.example/MoMaTo?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&Trusted_Connection=yes
   ```

**Prove it first on a scratch database.** The test suite runs against any database named in
`MOMATO_TEST_DATABASE_URL`. It **empties that database before every test**, so never point it at
a database with real data:

```powershell
$env:MOMATO_TEST_DATABASE_URL = "mssql+pyodbc://...@sqlserver/MoMaToTest?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes"
uv run --extra mssql pytest tests/api tests/integration
```

The DDL has been compiled for MS SQL offline (`tests/unit/test_mssql_schema.py`), and every
statement is held to the 2,100-parameter limit in the test suite, but the suites have not run on
a real SQL Server yet: expect to fix small things the first time, and report them.

There is no tool yet to move an existing SQLite database to MS SQL; start MS SQL with a fresh
installation (the profile and the org tree can be set up again in minutes) or ask for one.

## Backups

State is the database and `uploads/`. MoMaTo has no backup command of its own yet.

- **SQLite:** with the service stopped, copy the data folder (`momato.sqlite3` and `uploads/`;
  leave the `-wal` and `-shm` files with it). Without stopping: `sqlite3 momato.sqlite3 ".backup
  'backup.sqlite3'"` makes a consistent copy while the app runs; copy `uploads/` along with it.
- **MS SQL:** the DBA's `BACKUP DATABASE`; copy `uploads/` separately.

Schedule it daily (Task Scheduler on Windows, a systemd timer on Linux), keep a few generations,
copy them off the machine, and try a restore once: unpack into an empty folder, start MoMaTo with
`MOMATO_DATA_DIR` and `MOMATO_PORT` pointing at it, and look around.

## Upgrading

1. Take a backup (above).
2. Stop the service, replace the code, run `uv sync --frozen --no-dev` (plus `--extra mssql` if
   used).
3. Start the service: migrations run automatically.

With more than one process on the same database (not the default), set
`MOMATO_AUTO_MIGRATE=false` and run `python -m momato db upgrade` once during step 2, so two
processes never migrate at the same time.

## Security checklist

- TLS and HSTS at the proxy; the app only on `127.0.0.1`. (With Windows sign-in and no proxy:
  TLS by the app, and the private key readable by the service account only.)
- `MOMATO_TRUSTED_PROXIES` lists the proxy and nothing else.
- The `admin` password is changed (it is the break-glass account).
- The data folder and the `.env` file are readable by the service account only.
- The proxy accepts uploads of at least 10 MB (remark images); the app enforces the real limit.
- The app sends its own security headers (strict CSP, no framing, no sniffing); keep the proxy
  from overriding them.
- Backups run, are copied off the machine, and a restore has been tried once.
- API tokens: people create them on their Profile page; Administration › People › a person lists
  and revokes theirs.

## Checks before a release

Automated (`uv run python scripts/check.py --fix --e2e`): lint, types, import contracts,
traceability (every requirement ID has a test), unit/API/integration tests with the coverage
gates, JavaScript tests, and the browser tests with axe in all four appearances. Before a release
also run the opt-in suites:

```sh
uv run pytest -m scale          # the budgets of REQUIREMENTS 8.5 on 5,000 projects, 500 people
uv run pytest -m visual         # screenshots against tests/e2e/baselines
MOMATO_UPDATE_VISUAL=1 uv run pytest -m visual    # accept intended visual changes
```

By hand, on the deployed server (a quarter of an hour):

- [ ] The page loads over HTTPS, the console is clean, nothing is requested from another origin.
- [ ] `admin` can sign in, and the forced password change works.
- [ ] A person created under Administration › People signs in and sees what their roles allow.
- [ ] Create a project, edit a field, post a remark with an image, see the logbook.
- [ ] Book time on the timesheet, submit the week, see it in People planning (Spent).
- [ ] A person without *Hours viewer* on a branch sees no one else's time there.
- [ ] Export the project list as CSV and Excel and open both in Excel.
- [ ] Single sign-on (if configured): a prepared person signs in and gets exactly their rights;
      a stranger is refused.
- [ ] A token created on the Profile page works with `GET /api/auth/me`, and stops after revoking.
- [ ] Restart the service: sessions survive, nothing is lost.
