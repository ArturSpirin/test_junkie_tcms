"""Feature tree keyboard: arrows, one tab stop and a keyboard move, under node on the real tree data."""

import functools
import json
import shutil
import subprocess
from pathlib import Path

from test_junkie.decorators import Suite, test

HERE = Path(__file__).parent
TREE_JS = HERE.parent.parent / "src" / "test_junkie_tcms" / "web" / "js" / "views" / "tree.js"
NO_ROWS = {"empty-product", "loading", "error", "search-empty"}


@functools.cache
def keys() -> dict:
    node = shutil.which("node")
    if node is None:
        raise AssertionError(
            "node is not on PATH: the tree keyboard tests need node (no packages) to run "
            "tests/web/tree_keys.mjs. Install node; these tests never skip."
        )
    proc = subprocess.run(
        [node, str(HERE / "tree_keys.mjs")], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert proc.returncode == 0, f"tree_keys.mjs exited {proc.returncode}:\n{proc.stderr}"
    return json.loads(proc.stdout)


def focus_path(name: str) -> list:
    return [step["focus"] for step in keys()["nav"][name]]


@Suite()
class TreeKeyboard:
    @test()
    def test_arrows_move_between_visible_rows(self):
        assert focus_path("down") == ["f-card", "c-PAY-101", "c-PAY-102"]
        assert focus_path("homeEnd") == ["f-payouts", "f-checkout", "f-checkout"]

    @test()
    def test_left_collapses_then_right_on_a_leaf_does_nothing(self):
        steps = keys()["nav"]["collapse"]
        assert steps[0]["result"] == {"toggle": "f-card"}
        # f-card is closed now, so the next row down is f-wallet, which has no kids
        assert [s["focus"] for s in steps] == ["f-card", "f-wallet", "f-wallet", "f-wallet"]
        assert steps[2]["result"] is None

    @test()
    def test_left_on_a_case_goes_to_its_feature_then_collapses_it(self):
        steps = keys()["nav"]["leftFromCase"]
        assert [s["result"] for s in steps] == [{"focus": "f-card"}, {"toggle": "f-card"}]

    @test()
    def test_enter_opens_the_focused_case(self):
        steps = keys()["nav"]["enterCase"]
        assert steps[0]["result"] == {"open": "?view=case"}
        assert steps[1]["result"] is None

    @test()
    def test_a_lost_focus_comes_back_to_the_first_row(self):
        assert focus_path("missing") == ["f-checkout"]

    @test()
    def test_the_tree_has_one_tab_stop(self):
        for state, n in keys()["tabstops"].items():
            want = 0 if state in NO_ROWS else 1
            assert n["zero"] == want, f"tree#{state} has {n['zero']} rows with tabindex=0, want {want}"

    @test()
    def test_the_drop_bar_steps_through_the_places_drag_reaches(self):
        k = keys()
        assert k["slots140"] == {
            "first": {"id": "f-wallet", "z": "before"},
            "second": {"id": "f-wallet", "z": "in"},
            "up": {"id": "c-PAY-131", "z": "after"},
        }
        down = [(s["id"], s["z"]) for s in k["down140"]]
        assert len(down) == len(set(down)), "a place shows twice"
        # one place per gap: "before f-3ds" is the same gap as "after f-wallet"
        assert ("f-3ds", "before") not in down
        refused = {(s["id"], s["z"]) for s in k["down140"] if s["why"]}
        # a case can't sit at the product root
        top = {("f-refunds", "before"), ("f-subs", "before"), ("f-payouts", "before"), ("f-payouts", "after")}
        assert refused == top

    @test()
    def test_check_refuses_what_drag_refuses(self):
        r = keys()["refusals"]
        assert r["caseAtRoot"].startswith("A case has to sit inside a feature")
        assert "can't go inside itself" in r["featureInOwnKid"]
        assert r["caseInWallet"] == ""

    @test()
    def test_a_keyboard_move_puts_the_case_in_the_feature(self):
        assert keys()["moveIn"] == {
            "parent": "f-wallet",
            "wallet": ["c-PAY-140"],
            "card": ["c-PAY-101", "c-PAY-102", "c-PAY-118", "c-PAY-131"],
        }

    @test()
    def test_after_an_open_feature_that_is_last_in_its_list_is_a_place(self):
        last = keys()["lastOpen"]
        assert last["after"] >= 0, "after f-subs (open, last at the top) is missing"
        assert last["after"] > last["prorate"], "after f-subs must come below its kid f-prorate"
        assert last["placed"] == {"parent": None, "top": ["f-checkout", "f-refunds", "f-subs", "f-partial"]}

    @test()
    def test_the_tree_listens_for_keys_and_shares_the_drop_marks_with_drag(self):
        src = TREE_JS.read_text(encoding="utf-8")
        assert 'addEventListener("keydown"' in src
        assert src.count("markDrop(") >= 3, "dragover and the keyboard move both mark drops via markDrop()"
