"""A small catalog to test against: one product with a feature tree, a release and a plan."""

ORG = "/api/v1/orgs/{org}"


def url(path: str, org: str = "acme") -> str:
    return ORG.format(org=org) + path


def ok(response, status: int = 200) -> dict:
    assert response.status_code == status, response.text
    return response.json()


def make_product(client, key: str = "PAY", org: str = "acme", **body) -> dict:
    body.setdefault("name", f"{key} product")
    return ok(client.post(url("/products", org), json={"key": key, **body}), 201)


def make_feature(client, product: str, name: str, org: str = "acme", **body) -> dict:
    return ok(client.post(url(f"/products/{product}/features", org), json={"name": name, **body}), 201)


def make_release(client, product: str, version: str = "1.0", org: str = "acme", **body) -> dict:
    body.setdefault("name", f"Release {version}")
    return ok(client.post(url(f"/products/{product}/releases", org), json={"version": version, **body}), 201)


def make_plan(client, product: str, name: str = "Smoke", org: str = "acme", **body) -> dict:
    return ok(client.post(url(f"/products/{product}/plans", org), json={"name": name, **body}), 201)


def seed(client, key: str = "PAY", org: str = "acme") -> dict:
    """Product, a parent and child feature, a release listing the child, and a plan with one entry."""
    product = make_product(client, key, org)
    parent = make_feature(client, product["id"], "Checkout", org)
    child = make_feature(client, product["id"], "Card", org, parent_id=parent["id"])
    release = make_release(client, product["id"], org=org)
    ok(client.put(url(f"/releases/{release['id']}/features", org), json={"feature_ids": [child["id"]]}))
    plan = make_plan(client, product["id"], org=org, release_id=release["id"])
    plan = ok(
        client.post(url(f"/plans/{plan['id']}/entries", org), json={"entries": [{"feature_id": child["id"]}]})
    )
    return {"product": product, "parent": parent, "child": child, "release": release, "plan": plan}


def events(owner, entity_type: str, org: str = "acme") -> list[dict]:
    return ok(owner.get(url("/audit", org), params={"entity_type": entity_type, "limit": 200}))["items"]


def operations(s: dict) -> list[tuple[str, str, str, str, dict | None]]:
    """Every catalog operation, aimed at the seeded rows: (operation, method, path, scope, body)."""
    p, f, c, r, plan = (
        s["product"]["id"],
        s["parent"]["id"],
        s["child"]["id"],
        s["release"]["id"],
        s["plan"]["id"],
    )
    entry = s["plan"]["entries"][0]["id"]
    return [
        ("products_list", "GET", "/products", "read", None),
        ("products_get", "GET", f"/products/{p}", "read", None),
        ("products_update", "PATCH", f"/products/{p}", "write:catalog", {"name": "X"}),
        ("products_archive", "POST", f"/products/{p}/archive", "write:catalog", None),
        ("features_list", "GET", f"/products/{p}/features", "read", None),
        ("features_create", "POST", f"/products/{p}/features", "write:catalog", {"name": "X"}),
        ("features_get", "GET", f"/features/{f}", "read", None),
        ("features_update", "PATCH", f"/features/{f}", "write:catalog", {"name": "X"}),
        ("features_move", "POST", f"/features/{c}/move", "write:catalog", {"parent_id": None, "position": 0}),
        ("features_archive", "POST", f"/features/{f}/archive", "write:catalog", None),
        ("releases_list", "GET", f"/products/{p}/releases", "read", None),
        (
            "releases_create",
            "POST",
            f"/products/{p}/releases",
            "write:catalog",
            {"version": "9", "name": "X"},
        ),
        ("releases_get", "GET", f"/releases/{r}", "read", None),
        ("releases_update", "PATCH", f"/releases/{r}", "write:catalog", {"name": "X"}),
        ("releases_set_features", "PUT", f"/releases/{r}/features", "write:catalog", {"feature_ids": [f]}),
        ("plans_list", "GET", f"/products/{p}/plans", "read", None),
        ("plans_create", "POST", f"/products/{p}/plans", "write:planning", {"name": "X"}),
        ("plans_get", "GET", f"/plans/{plan}", "read", None),
        ("plans_update", "PATCH", f"/plans/{plan}", "write:planning", {"name": "X"}),
        (
            "plans_add_entries",
            "POST",
            f"/plans/{plan}/entries",
            "write:planning",
            {"entries": [{"feature_id": f}]},
        ),
        ("plans_remove_entry", "DELETE", f"/plans/{plan}/entries/{entry}", "write:planning", None),
    ]


OPERATION_NAMES = [
    "products_list",
    "products_get",
    "products_update",
    "products_archive",
    "features_list",
    "features_create",
    "features_get",
    "features_update",
    "features_move",
    "features_archive",
    "releases_list",
    "releases_create",
    "releases_get",
    "releases_update",
    "releases_set_features",
    "plans_list",
    "plans_create",
    "plans_get",
    "plans_update",
    "plans_add_entries",
    "plans_remove_entry",
]


def call(client, op_name: str, s: dict, org: str = "acme"):
    [(_, method, path, _, body)] = [o for o in operations(s) if o[0] == op_name]
    return client.request(method, url(path, org), json=body)
