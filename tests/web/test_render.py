"""Web app views: every view renders every state of the approved mock from its data module, under node."""

import functools
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from test_junkie.decorators import Suite, test

HERE = Path(__file__).parent
MOCK_STATES = json.loads((HERE / "mock_states.json").read_text(encoding="utf-8"))
# Leaks of a missing or wrong value into the markup.
SUSPECT = re.compile(r"undefined|NaN|\[object |null<")
# What a footer must never show a tester or PM: an HTTP call ("PUT /releases/..."), or an MCP tool name. Plain
# one-word tools ("search") are left out: they are ordinary words in copy.
HTTP_CALL = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/")
MCP_TOOLS = sorted(
    t["name"]
    for t in json.loads((HERE.parent / "snapshots" / "mcp_tools.json").read_text(encoding="utf-8"))
    if "_" in t["name"]
)
MCP_TOOL = re.compile(r"\b(?:" + "|".join(map(re.escape, MCP_TOOLS)) + r")\b")
# Footers the guard must find, so it can never pass by seeing none: dialogs (.mf) and card bars (.foot-bar).
KNOWN_FOOTERS = {
    "tokens": ["create", "revoke-confirm"],
    "releases": ["set-features"],
    "start": ["scope", "cancel-cases", "stop-confirm"],
    "consumers": ["pair", "pair-approve", "detail"],
    "cases": ["list"],
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Footers(HTMLParser):
    """Collects each footer (a dialog's .mf, a card's .foot-bar): its text, and whether any of it is mono."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.footers: list[dict] = []
        self.depth = 0  # open elements inside the current footer; 0 = not in one

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if self.depth == 0 and ("mf" in classes or "foot-bar" in classes):
            self.footers.append({"text": "", "mono": False})
            self.depth = 1
        elif self.depth:
            self.footers[-1]["mono"] |= "mono" in classes
            if tag not in VOID:
                self.depth += 1

    def handle_endtag(self, tag):
        if self.depth and tag not in VOID:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.footers[-1]["text"] += " " + data  # elements are separate words: "tokens_revoke" "Cancel"


def footers(html: str) -> list[dict]:
    parser = Footers()
    parser.feed(html)
    parser.close()
    return parser.footers


@functools.cache
def rendered() -> dict:
    node = shutil.which("node")
    if node is None:
        raise AssertionError(
            "node is not on PATH: the web view render tests need node (no packages) to run "
            "tests/web/render_states.mjs. Install node; these tests never skip."
        )
    proc = subprocess.run(
        [node, str(HERE / "render_states.mjs")], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert proc.returncode == 0, f"render_states.mjs exited {proc.returncode}:\n{proc.stderr}"
    return json.loads(proc.stdout)


@Suite()
class WebViews:
    @test()
    def test_the_app_has_exactly_the_mock_views(self):
        assert sorted(rendered()) == sorted(MOCK_STATES)

    @test(parameters=sorted(MOCK_STATES))
    def test_view_has_exactly_the_mock_states(self, parameter):
        assert sorted(rendered()[parameter]) == sorted(MOCK_STATES[parameter])

    @test(parameters=sorted(MOCK_STATES))
    def test_every_state_renders_clean_html(self, parameter):
        for state, result in rendered()[parameter].items():
            where = f"{parameter}#{state}"
            assert "error" not in result, f"{where} threw:\n{result.get('error')}"
            html = result["html"]
            assert html.strip(), f"{where} rendered nothing"
            leak = SUSPECT.search(html)
            if leak is not None:
                context = html[max(0, leak.start() - 60) : leak.end() + 20]
                raise AssertionError(f"{where} shows {leak.group(0)!r}: ...{context}")
            assert result["again"], f"{where} rendered different HTML from the same data"

    @test(parameters=sorted(MOCK_STATES))
    def test_no_footer_shows_an_op_name(self, parameter):
        for state, result in rendered()[parameter].items():
            for n, f in enumerate(footers(result.get("html", "")), 1):
                where = f"{parameter}#{state} footer {n} ({' '.join(f['text'].split())[:80]!r})"
                assert not HTTP_CALL.search(f["text"]), f"{where} shows an HTTP call"
                tool = MCP_TOOL.search(f["text"])
                assert tool is None, f"{where} shows the MCP tool {tool.group(0) if tool else ''!r}"
                assert not f["mono"], f"{where} has monospace text: footers say plain words (ui.js foot())"

    @test(parameters=sorted(KNOWN_FOOTERS))
    def test_the_footer_guard_sees_the_known_footers(self, parameter):
        for state in KNOWN_FOOTERS[parameter]:
            html = rendered()[parameter][state]["html"]
            assert footers(html), f"{parameter}#{state}: the guard found no footer"
