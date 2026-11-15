"""T3's contract: case operations, optional Idempotency-Key on org POSTs, required If-Match on case writes."""

import pytest

CASE_OPS = {
    "cases_list": "read",
    "cases_create": "write:cases",
    "cases_get": "read",
    "cases_update": "write:cases",
    "cases_versions_list": "read",
    "cases_version_get": "read",
    "cases_restore": "write:cases",
    "cases_move": "write:cases",
    "cases_archive": "write:cases",
    "cases_bulk_upsert": "write:cases",
    "tags_list": "read",
}
NO_IDEMPOTENCY = {"tokens_create", "auth_login", "auth_logout"}  # a token's secret is never stored for replay
NO_IDEMPOTENCY |= {"pairings_create", "pairings_token", "consumers_heartbeat"}  # no org yet, or consumer-only
NO_IDEMPOTENCY |= {"jobs_report"}  # consumer-only
NO_IDEMPOTENCY |= {"invites_create", "invites_accept"}  # invite token never stored for replay
NO_IDEMPOTENCY |= {"attachments_upload", "attachments_upload_base64"}  # content dedupe makes a repeat safe
NO_IDEMPOTENCY |= {"cycles_preview"}  # writes nothing


@pytest.fixture
def spec(client_factory):
    response = client_factory().get("/api/v1/openapi.json")
    assert response.status_code == 200
    return response.json()["paths"]


def ops(paths, method=None):
    return {
        op["operationId"]: op
        for path in paths.values()
        for m, op in path.items()
        if isinstance(op, dict) and "operationId" in op and method in (None, m)
    }


def header(op, name):
    return next((p for p in op.get("parameters", []) if p["in"] == "header" and p["name"] == name), None)


@pytest.mark.parametrize("name", sorted(CASE_OPS))
def test_case_operation_is_marked(spec, name):
    op = ops(spec)[name]
    assert (op["x-scope"], op["x-toolset"], op["x-mcp"]) == (CASE_OPS[name], "cases", True)


def test_plans_resolve_is_a_planning_read(spec):
    op = ops(spec)["plans_resolve"]
    assert (op["x-scope"], op["x-toolset"]) == ("read", "planning")


def test_idempotency_key_is_optional_on_every_org_post(spec):
    posts = ops(spec, "post")
    assert "members_add" in posts and "agents_create" in posts and "cases_create" in posts
    for name, op in posts.items():
        param = header(op, "Idempotency-Key")
        if name in NO_IDEMPOTENCY:
            assert param is None, name
        else:
            assert param is not None and not param.get("required", False), name


def test_if_match_is_required_on_versioned_writes(spec):
    all_ops = ops(spec)
    for name in ("cases_update", "cases_restore"):
        assert header(all_ops[name], "If-Match")["required"] is True, name
    assert header(all_ops["cases_update"], "Idempotency-Key") is None  # PATCH is guarded by If-Match instead
