"""Command line interface: `python -m momato <command>`.

serve [--host H] [--port P] [--reload]   run the web server (HTTPS: MOMATO_TLS_CERTFILE, _KEYFILE)
db upgrade                               apply database migrations
seed [--sample [--demo-password PW]]     create built-in data; optionally load the sample data
create-admin [--password PW]             create or repair the built-in admin account
"""

import argparse
from collections.abc import Sequence

from momato.config import get_settings
from momato.db.session import Database
from momato.domain.fields import ProfileError
from momato.services.profile import load_profile
from momato.services.sample_data import load_sample_data
from momato.services.seed import reset_admin
from momato.services.setup import prepare_database

# Windows issues Kerberos tickets of up to 48,000 bytes (MaxTokenSize), sent base64-encoded:
# 64 kB in one request header, far above Uvicorn's default of 16 kB for all headers.
NEGOTIATE_HEADER_LIMIT = 128 * 1024


def _serve(args: argparse.Namespace) -> int:
    import uvicorn  # imported lazily: other commands don't need the server

    settings = get_settings()
    try:
        load_profile(settings.profile)
    except ProfileError as error:
        print(f"Cannot start: {error}")
        return 1
    if bool(settings.tls_certfile) != bool(settings.tls_keyfile):
        print("Cannot start: MOMATO_TLS_CERTFILE and MOMATO_TLS_KEYFILE must be set together.")
        return 1
    uvicorn.run(
        "momato.web:create_app",
        factory=True,
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
        proxy_headers=False,  # the app reads forwarded headers itself, only from trusted proxies
        ssl_certfile=str(settings.tls_certfile) if settings.tls_certfile else None,
        ssl_keyfile=str(settings.tls_keyfile) if settings.tls_keyfile else None,
        h11_max_incomplete_event_size=NEGOTIATE_HEADER_LIMIT if settings.windows_auth else None,
    )
    return 0


def _database() -> Database:
    return Database(get_settings().resolved_database_url)


def _db_upgrade(_args: argparse.Namespace) -> int:
    from momato.db.migrate import upgrade_database

    database = _database()
    upgrade_database(database.url)
    database.dispose()
    print("Database schema is up to date.")
    return 0


def _seed(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        profile = load_profile(settings.profile)
    except ProfileError as error:
        print(f"Cannot seed: {error}")
        return 1
    database = _database()
    admin_password = settings.initial_admin_password
    report = prepare_database(
        database,
        initial_admin_password=admin_password.get_secret_value() if admin_password else None,
    )
    for item in report.created:
        print(f"created {item}")
    if report.generated_admin_password:
        print(f"Admin password (change it at first login): {report.generated_admin_password}")
    if args.sample:
        with database.session(write=True) as session:
            loaded = load_sample_data(
                session,
                today=settings.current_date(),  # the sample's dates are moved to today (D-027)
                profile=profile,
                uploads_dir=settings.uploads_dir,
                demo_password=args.demo_password,
            )
        print(
            "Loaded the sample data."
            if loaded
            else "The database already holds projects: sample data not loaded."
        )
    database.dispose()
    return 0


def _create_admin(args: argparse.Namespace) -> int:
    database = _database()
    prepare_database(database)
    with database.session(write=True) as session:
        password, generated = reset_admin(session, password=args.password)
    database.dispose()
    if generated:
        print(f"Admin password (change it at first login): {password}")
    else:
        print("The admin account is ready; sign in with the password you gave.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m momato",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the web server")
    serve.add_argument("--host", help="interface to bind (default: MOMATO_HOST or 127.0.0.1)")
    serve.add_argument("--port", type=int, help="port (default: MOMATO_PORT or 8000)")
    serve.add_argument("--reload", action="store_true", help="restart on code changes (dev only)")
    serve.set_defaults(handler=_serve)

    seed = commands.add_parser("seed", help="create built-in data, optionally the sample data")
    seed.add_argument("--sample", action="store_true", help="load the sample data if empty")
    seed.add_argument(
        "--demo-password", help="let the sample people sign in with this password (demos only)"
    )
    seed.set_defaults(handler=_seed)

    create_admin = commands.add_parser(
        "create-admin", help="create or repair the built-in admin account"
    )
    create_admin.add_argument(
        "--password", help="its password (default: generate one, to be changed at first login)"
    )
    create_admin.set_defaults(handler=_create_admin)

    db = commands.add_parser("db", help="database maintenance")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser("upgrade", help="apply migrations").set_defaults(handler=_db_upgrade)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
