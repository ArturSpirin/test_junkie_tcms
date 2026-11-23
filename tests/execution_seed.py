"""Cases and cycles to test execution (T4) against, on top of catalog_seed."""

from tests.catalog_seed import ok, seed, url

STEPS = [
    {"action": {"markdown": "Open the cart"}, "expected": {"markdown": "The cart opens"}},
    {"action": {"markdown": "Pay by card"}, "expected": {"markdown": "The order is paid"}},
]


def make_case(client, product: str, feature: str, title: str, org: str = "acme", **body) -> dict:
    body = {"feature_id": feature, "title": title, **body}
    return ok(client.post(url(f"/products/{product}/cases", org), json=body), 201)


def activate(client, plan: str, org: str = "acme") -> dict:
    return ok(client.patch(url(f"/plans/{plan}", org), json={"status": "active"}))


def make_cycle(client, product: str, org: str = "acme", **body) -> dict:
    body.setdefault("name", "Run")
    return ok(client.post(url(f"/products/{product}/cycles", org), json=body), 201)


def cycle_cases(client, cycle: str, org: str = "acme", **params) -> list[dict]:
    return ok(client.get(url(f"/cycles/{cycle}/cases", org), params=params))["items"]


def record(client, cycle_case: str, org: str = "acme", **body):
    return client.post(url(f"/cycle-cases/{cycle_case}/results", org), json=body)


def edit_steps(owner, case: dict, version: int = 1) -> dict:
    """Version 2: the first step reworded (same id), the second dropped, a new one added."""
    first = case["steps"][0]
    steps = [
        {"id": first["id"], "action": {"markdown": "Open the basket"}, "expected": {"markdown": "It opens"}},
        {"action": {"markdown": "Pay by voucher"}, "expected": {"markdown": "The order is paid"}},
    ]
    return ok(
        owner.patch(url(f"/cases/{case['key']}"), json={"steps": steps}, headers={"If-Match": f'"{version}"'})
    )


def run_seed(client, key: str = "PAY", org: str = "acme") -> dict:
    """The catalog seed plus one two-step case under the child feature, in an open cycle."""
    s = seed(client, key, org)
    case = make_case(client, s["product"]["id"], s["child"]["id"], "Pay by card", org, steps=STEPS)
    cycle = make_cycle(client, s["product"]["id"], org, case_ids=[case["id"]])
    [cc] = cycle_cases(client, cycle["id"], org)
    return {**s, "case": case, "cycle": cycle, "cycle_case": cc}
