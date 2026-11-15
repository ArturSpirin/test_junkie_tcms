"""The tenancy rule (PLAN-27 §3) holds for every table, and the check catches a table that breaks it."""

from sqlalchemy import Column, ForeignKey, ForeignKeyConstraint, MetaData, String, Table, UniqueConstraint

from test_junkie_tcms.db.base import GLOBAL_TABLES, PRE_TENANT_TABLES, Base
from test_junkie_tcms.db.tenancy import tenancy_violations


def _copy() -> MetaData:
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)
    return metadata


def test_every_tenant_table_follows_the_rule():
    assert tenancy_violations(Base.metadata) == []


def test_tenant_tables_are_the_expected_ones():
    tenant = set(Base.metadata.tables) - set(GLOBAL_TABLES)
    assert tenant == {
        "membership",
        "actor",
        "api_token",
        "invite",
        "audit_event",
        "outbox",
        "product",
        "feature",
        "release",
        "release_feature",
        "test_plan",
        "plan_entry",
        "test_case",
        "case_version",
        "tag",
        "case_version_tag",
        "idempotency_record",
        "consumer",
        "consumer_product",
        "pairing_request",
        "consumer_heartbeat",
        "consumer_inventory",
        "cycle_batch",
        "cycle",
        "cycle_case",
        "result",
        "result_attachment",
        "attachment",
        "job",
        "mcp_tool_stat",
    }


def test_nullable_org_id_passes_only_for_pre_tenant_tables():
    metadata = _copy()
    for name in ("early", "late"):
        Table(
            name,
            metadata,
            Column("id", String(26), primary_key=True),
            Column("org_id", String(26), ForeignKey("org.id"), nullable=True),
            UniqueConstraint("org_id", "id"),
        )
    pre_tenant = {**PRE_TENANT_TABLES, "early": "test"}
    assert tenancy_violations(metadata, pre_tenant_tables=pre_tenant) == ["late: org_id is nullable"]


def test_table_without_org_id_fails():
    metadata = _copy()
    Table("loose", metadata, Column("id", String(26), primary_key=True))
    assert tenancy_violations(metadata) == ["loose: no org_id column"]


def test_nullable_org_id_without_fk_or_unique_fails():
    metadata = _copy()
    Table(
        "sloppy",
        metadata,
        Column("id", String(26), primary_key=True),
        Column("org_id", String(26), nullable=True),
    )
    assert tenancy_violations(metadata) == [
        "sloppy: org_id is nullable",
        "sloppy: org_id has no FK to org",
        "sloppy: no UNIQUE(org_id, id)",
    ]


def test_single_column_fk_to_tenant_table_fails():
    metadata = _copy()
    Table(
        "case_note",
        metadata,
        Column("id", String(26), primary_key=True),
        Column("org_id", String(26), ForeignKey("org.id"), nullable=False),
        Column("actor_id", String(26), ForeignKey("actor.id"), nullable=False),
        UniqueConstraint("org_id", "id"),
    )
    assert tenancy_violations(metadata) == ["case_note: FK ['actor_id'] -> actor is not composite on org_id"]


def test_fk_to_global_table_fails():
    metadata = _copy()
    Table(
        "case_note",
        metadata,
        Column("id", String(26), primary_key=True),
        Column("org_id", String(26), ForeignKey("org.id"), nullable=False),
        Column("user_id", String(26), ForeignKey("user.id"), nullable=False),
        UniqueConstraint("org_id", "id"),
    )
    assert tenancy_violations(metadata) == ["case_note: FK ['user_id'] -> global table user is not allowed"]


def test_composite_fk_passes():
    metadata = _copy()
    Table(
        "case_note",
        metadata,
        Column("id", String(26), primary_key=True),
        Column("org_id", String(26), ForeignKey("org.id"), nullable=False),
        Column("actor_id", String(26), nullable=False),
        UniqueConstraint("org_id", "id"),
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
    )
    assert tenancy_violations(metadata) == []
