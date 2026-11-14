from alembic import command
from alembic.config import Config


def alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "test_junkie_tcms:migrations")
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def upgrade(database_url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)
