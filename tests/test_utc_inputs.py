"""Every API time input goes through `aware()`, the one UTC rule: a caller's offset never reaches a query."""

import types
from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated, Union, get_args, get_origin

from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import AwareDatetime, BaseModel
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.base import aware
from tests import support

# The datetime inputs this guard is known to cover; it must find at least these, so it can't pass on none.
KNOWN = {
    "GET /api/v1/orgs/{org}/audit since",
    "GET /api/v1/orgs/{org}/audit until",
    "GET /api/v1/orgs/{org}/products/{product}/cases updated_since",
    "GET /api/v1/orgs/{org}/mcp/tools since",
    "GET /api/v1/orgs/{org}/mcp/tools until",
    "GET /api/v1/orgs/{org}/mcp/usage since",
    "GET /api/v1/orgs/{org}/mcp/usage until",
    "GET /api/v1/orgs/{org}/mcp/clients since",
    "GET /api/v1/orgs/{org}/mcp/clients until",
    "GET /api/v1/orgs/{org}/mcp/calls since",
    "GET /api/v1/orgs/{org}/mcp/calls until",
    "POST /api/v1/orgs/{org}/tokens expires_at",
    "POST /api/v1/orgs/{org}/products/{product}/releases released_at",
    "PATCH /api/v1/orgs/{org}/releases/{id} released_at",
}


def _is_aware(item) -> bool:
    return getattr(item, "func", None) is aware


def _times(annotation, metadata, seen) -> list[tuple[str, bool]]:
    """Each datetime in `annotation` (through Annotated, unions, lists, nested models) as (path, has aware)."""
    if get_origin(annotation) is Annotated:
        base, *extra = get_args(annotation)
        return _times(base, [*metadata, *extra], seen)
    # pydantic's AwareDatetime is a marker class, not a datetime subclass.
    if isinstance(annotation, type) and issubclass(annotation, (datetime, AwareDatetime)):
        return [("", any(_is_aware(item) for item in metadata))]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return []
        found = []
        for name, field in annotation.model_fields.items():
            for path, ok in _times(field.annotation, field.metadata, seen | {annotation}):
                found.append((f".{name}{path}", ok))
        return found
    found = []
    # A union keeps the outer metadata off its members: `UtcDateTime | None` carries it inside.
    inner = metadata if get_origin(annotation) not in (Union, types.UnionType) else []
    for arg in get_args(annotation):
        found += _times(arg, inner, seen)
    return found


def _inputs(app) -> dict[str, bool]:
    found: dict[str, bool] = {}

    def walk(dependant, label):
        params = dependant.query_params + dependant.path_params + dependant.header_params
        for field in params + dependant.cookie_params + dependant.body_params:
            for path, ok in _times(field.field_info.annotation, field.field_info.metadata, frozenset()):
                name = path[1:] if field in dependant.body_params and path else field.name + path
                found[f"{label} {name}"] = ok
        for sub in dependant.dependencies:
            walk(sub, label)

    # Included routers are wrapped, not copied, onto the app: walk them as the OpenAPI builder does.
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        if isinstance(route, APIRoute):
            for method in sorted(route.methods):
                walk(route.dependant, f"{method} {context.path}")
    return found


@Suite(parameters=support.DATABASES[:1])
class UtcInputs:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    @test()
    def test_every_datetime_input_goes_through_aware(self, suite_parameter):
        found = _inputs(self.env.app)
        missing = sorted(KNOWN - set(found))
        assert not missing, f"The guard no longer sees: {missing}"
        skipped = sorted(name for name, ok in found.items() if not ok)
        assert not skipped, f"Datetime inputs without UtcDateTime: {skipped}"

    @test()
    def test_aware_keeps_the_instant_and_makes_it_utc(self, suite_parameter):
        base = datetime(2026, 11, 14, 3, 0)
        assert aware(base) == base.replace(tzinfo=UTC) and aware(None) is None
        for quarter in range(-14 * 4, 14 * 4 + 1):
            given = base.replace(tzinfo=timezone(timedelta(minutes=15 * quarter)))
            made = aware(given)
            assert made == given and made.utcoffset() == timedelta(0), given.isoformat()
