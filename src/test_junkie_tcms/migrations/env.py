from alembic import context

from test_junkie_tcms.db import models  # noqa: F401  (registers the tables)
from test_junkie_tcms.db.base import Base
from test_junkie_tcms.db.session import make_engine
from test_junkie_tcms.settings import Settings

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or Settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # Batch mode rebuilds a table (copy, DROP, rename), which SQLite refuses while other rows
            # reference it and foreign keys are enforced. SQLite's own rebuild procedure turns them off for
            # the change and checks them after. The pragma is a no-op inside a transaction, so it goes first.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=sqlite)
        with context.begin_transaction():
            context.run_migrations()
            if sqlite:
                broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise RuntimeError(f"migration left rows with broken foreign keys: {broken[:5]}")
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
