"""Names: a product, feature, release, plan or cycle name of only spaces is a 422.

Spaces around a name are stripped.
"""

from pydantic import BaseModel, ValidationError
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.api.v1 import execution_schemas, schemas
from tests import support
from tests.catalog_seed import make_release, ok, seed, url
from tests.execution_seed import activate, make_case, make_cycle

BLANK = ("", "   ", "\t \n")


def request_models(openapi: dict) -> set[str]:
    """Every component a request body refers to, directly or nested."""
    components = openapi["components"]["schemas"]
    seen: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref:
                name = ref.rsplit("/", 1)[-1]
                if name not in seen:
                    seen.add(name)
                    walk(components[name])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path in openapi["paths"].values():
        for operation in path.values():
            if isinstance(operation, dict):
                walk(operation.get("requestBody"))
    return seen


@Suite(parameters=support.DATABASES)
class Names:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def s(self) -> dict:
        owner = self.env.owner
        s = seed(owner)
        make_case(owner, s["product"]["id"], s["child"]["id"], "Pay by card")
        s["cycle"] = make_cycle(owner, s["product"]["id"], name="Nightly")
        return s

    def writes(self, s: dict, name: str) -> list[tuple[str, str, dict]]:
        """Every API write that takes a name: (method, path, body)."""
        p = s["product"]["id"]
        return [
            ("POST", "/products", {"key": "NEW", "name": name}),
            ("PATCH", f"/products/{p}", {"name": name}),
            ("POST", f"/products/{p}/features", {"name": name}),
            ("PATCH", f"/features/{s['child']['id']}", {"name": name}),
            ("POST", f"/products/{p}/releases", {"version": "9.0", "name": name}),
            ("PATCH", f"/releases/{s['release']['id']}", {"name": name}),
            ("POST", f"/products/{p}/plans", {"name": name}),
            ("PATCH", f"/plans/{s['plan']['id']}", {"name": name}),
            ("POST", f"/products/{p}/cycles", {"name": name}),
            ("PATCH", f"/cycles/{s['cycle']['id']}", {"name": name}),
            ("POST", f"/releases/{s['release']['id']}/cycles/bulk", {"mode": "plans", "name": name}),
        ]

    def names(self, s: dict) -> dict:
        owner, p = self.env.owner, s["product"]["id"]
        return {
            "products": [x["name"] for x in ok(owner.get(url("/products")))["items"]],
            "features": [x["name"] for x in ok(owner.get(url(f"/products/{p}/features")))["items"]]
            + [ok(owner.get(url(f"/features/{s['child']['id']}")))["name"]],
            "releases": [x["name"] for x in ok(owner.get(url(f"/products/{p}/releases")))["items"]],
            "plans": [x["name"] for x in ok(owner.get(url(f"/products/{p}/plans")))["items"]],
            "cycles": [x["name"] for x in ok(owner.get(url(f"/products/{p}/cycles")))["items"]],
        }

    @test()
    def test_a_name_of_only_spaces_is_a_422_on_every_write(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        activate(owner, s["plan"]["id"])  # so a bulk batch would make a cycle
        before = self.names(s)
        for name in BLANK:
            for method, path, body in self.writes(s, name):
                r = owner.request(method, url(path), json=body)
                assert r.status_code == 422, (method, path, repr(name), r.text)
                assert [e["loc"] for e in r.json()["errors"]] == [["body", "name"]], (path, r.text)
        assert self.names(s) == before

    @test()
    def test_spaces_around_a_name_are_stripped(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        activate(owner, s["plan"]["id"])
        p = s["product"]["id"]
        created = {
            path: ok(owner.post(url(path), json=body), 201)
            for _, path, body in self.writes(s, " \tX  ")[0::2]
        }
        assert created["/products"]["name"] == "X"
        for path in (f"/products/{p}/features", f"/products/{p}/releases", f"/products/{p}/plans"):
            assert created[path]["name"] == "X", path
        assert created[f"/products/{p}/cycles"]["name"] == "X"
        [batch] = created[f"/releases/{s['release']['id']}/cycles/bulk"]["cycles"]
        assert batch["name"] == "X · Smoke"
        for _, path, body in self.writes(s, "  Renamed ")[1::2]:
            assert ok(owner.patch(url(path), json=body))["name"] == "Renamed", path
        long = " " + "x" * 200 + " "
        # The length limit counts after stripping.
        assert make_release(owner, p, "9.1", name=long)["name"] == "x" * 200

    @test()
    def test_every_request_name_field_refuses_only_spaces(self, suite_parameter):
        """The guard: every request model with a `name`, in a route body or nested in one, strips it."""
        openapi = self.env.client().get("/api/v1/openapi.json").json()
        classes = {
            n: c
            for mod in (schemas, execution_schemas)
            for n, c in vars(mod).items()
            if isinstance(c, type) and issubclass(c, BaseModel) and c.__module__ == mod.__name__
        }
        components = openapi["components"]["schemas"]
        checked = []
        for component in sorted(request_models(openapi)):
            if "name" not in components[component].get("properties", {}):
                continue
            model = classes[component.removesuffix("-Input")]
            try:
                model.model_validate({"name": "   "})
                errors = []
            except ValidationError as e:
                errors = [x["type"] for x in e.errors() if x["loc"] == ("name",)]
            assert errors == ["string_too_short"], (component, errors)
            checked.append(model.__name__)
        for model in (
            "ProductCreate",
            "FeatureUpdate",
            "PlanCreate",
            "CycleCreate",
            "BulkCycleCreate",
            "OrgUpdate",
        ):
            assert model in checked, (model, checked)
