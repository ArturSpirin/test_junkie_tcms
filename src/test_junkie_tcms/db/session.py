from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from test_junkie_tcms.db.models import AuditEvent


class AuditAppendOnlyError(RuntimeError):
    pass


def make_engine(url: str) -> Engine:
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_foreign_keys(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(Session, "before_flush")
def _audit_append_only(session: Session, _ctx, _instances) -> None:
    for obj in session.deleted:
        if isinstance(obj, AuditEvent):
            raise AuditAppendOnlyError("audit_event is append-only")
    for obj in session.dirty:
        if isinstance(obj, AuditEvent) and session.is_modified(obj):
            raise AuditAppendOnlyError("audit_event is append-only")
