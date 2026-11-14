"""`test-junkie-tcms serve | migrate | create-admin`."""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from test_junkie_tcms.auth.passwords import hash_password
from test_junkie_tcms.db import migrate
from test_junkie_tcms.db.models import Actor, Membership, Org, User
from test_junkie_tcms.db.session import make_engine, make_sessionmaker
from test_junkie_tcms.settings import Settings


def create_admin(
    settings: Settings, email: str, name: str, org_slug: str, org_name: str, password: str
) -> None:
    """Make the first user, their org, the owner membership and the user actor, in one transaction."""
    engine = make_engine(settings.database_url)
    try:
        with make_sessionmaker(engine)() as db, db.begin():
            email = email.strip().lower()
            if db.scalar(select(User).where(User.email == email)) is not None:
                raise SystemExit(f"A user with email {email} already exists")
            if db.scalar(select(Org).where(Org.slug == org_slug)) is not None:
                raise SystemExit(f"An org with slug {org_slug} already exists")
            user = User(email=email, name=name, password_hash=hash_password(password))
            org = Org(slug=org_slug, name=org_name)
            db.add_all([user, org])
            db.flush()
            db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
            db.flush()
            db.add(Actor(org_id=org.id, kind="user", name=name, user_id=user.id))
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="test-junkie-tcms")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="apply migrations, then run the server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("migrate", help="apply database migrations")
    admin = sub.add_parser("create-admin", help="create the first user and org")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.add_argument("--org-slug", required=True)
    admin.add_argument("--org-name", required=True)
    args = parser.parse_args(argv)
    settings = Settings()

    if args.command == "migrate":
        migrate.upgrade(settings.database_url)
    elif args.command == "serve":
        import uvicorn

        from test_junkie_tcms.app import create_app

        migrate.upgrade(settings.database_url)
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
    elif args.command == "create-admin":
        password = os.environ.get("TJ_TCMS_ADMIN_PASSWORD") or getpass.getpass("Password: ")
        if len(password) < 8:
            sys.exit("The password needs at least 8 characters")
        create_admin(settings, args.email, args.name, args.org_slug, args.org_name, password)
        print(f"Created {args.email} as owner of {args.org_slug}")


if __name__ == "__main__":
    main()
