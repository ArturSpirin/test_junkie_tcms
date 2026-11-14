from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from test_junkie_tcms.db.models import AuditEvent, CaseVersion, CaseVersionTag


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


class CaseVersionImmutableError(RuntimeError):
    pass


IMMUTABLE = (CaseVersion, CaseVersionTag)
IMMUTABLE_TABLES = {m.__tablename__ for m in IMMUTABLE}


@event.listens_for(Session, "before_flush")
def _case_versions_immutable(session: Session, _ctx, _instances) -> None:
    """A case version and its tags are written once: every edit adds a new version instead."""
    for obj in session.deleted:
        if isinstance(obj, IMMUTABLE):
            raise CaseVersionImmutableError(f"{obj.__tablename__} is immutable")
    for obj in session.dirty:
        if isinstance(obj, IMMUTABLE) and session.is_modified(obj):
            raise CaseVersionImmutableError(f"{obj.__tablename__} is immutable")


@event.listens_for(Session, "do_orm_execute")
def _case_versions_no_bulk_writes(state) -> None:
    """The same rule for `update()` / `delete()` statements run through a session."""
    if state.is_update or state.is_delete:
        table = getattr(state.statement, "table", None)
        if table is not None and table.name in IMMUTABLE_TABLES:
            raise CaseVersionImmutableError(f"{table.name} is immutable")
