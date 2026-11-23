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
# What no view may show a tester or PM (an API op is a builder note, not UI): an HTTP call
# ("PUT /releases/..."), or an MCP tool name. Plain one-word tools ("search") are left out: they are
# ordinary words in copy.
HTTP_CALL = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[^\s<>\"']*")
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
# Toasts the guard must find: each state that shows one (state.toast in its view).
KNOWN_TOASTS = {
    "tree": ["desc-saved", "search-cleared"],
    "members": ["role-changed", "removed", "invite-revoked"],
    "products": ["created", "search-cleared"],
    "cases": ["search-cleared"],
    "plans": ["search-cleared"],
    "start": ["reassigned"],
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# Attributes a person sees or hears: tooltips, labels, placeholders. A tooltip may itself hold markup.
SHOWN_ATTRS = ("title", "aria-label", "placeholder", "alt", "value", "data-tip")


class Shown(HTMLParser):
    """Collects everything a page shows a person: its text (not script or style) and the shown attributes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0  # inside <script> or <style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        for name, value in attrs:
            if name in SHOWN_ATTRS and value:
                self.parts.append(shown(value))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def shown(html: str) -> str:
    """The text a person sees in the markup, elements as separate words: "<b>PUT</b> /x" reads "PUT /x"."""
    parser = Shown()
    parser.feed(html)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


def op_names(text: str, data: list[str]) -> list[str]:
    """The API or MCP op names the text shows that are not the state's own data. Data is what the server or a
    user wrote (an error message, an audit event's tool, a run note) and always shows raw, word for word."""
    raw = [" ".join(s.split()) for s in data]
    hits = [m.group(0).rstrip(".,;:)]·") for m in HTTP_CALL.finditer(text)] + MCP_TOOL.findall(text)
    return [h for h in hits if not any(h in s for s in raw)]


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
    def test_no_view_shows_an_op_name(self, parameter):
        found = []
        for state, result in rendered()[parameter].items():
            for part in ("html", "toast"):
                ops = op_names(shown(result.get(part, "")), result.get("data", []))
                found += [
                    f"{parameter}#{state} {'toast' if part == 'toast' else 'page'}: {op!r}" for op in ops
                ]
        assert not found, "views show API or MCP op names (say it in plain words, or drop it):\n" + "\n".join(
            found
        )

    @test(parameters=sorted(MOCK_STATES))
    def test_no_footer_is_monospace(self, parameter):
        for state, result in rendered()[parameter].items():
            for n, f in enumerate(footers(result.get("html", "")), 1):
                where = f"{parameter}#{state} footer {n} ({' '.join(f['text'].split())[:80]!r})"
                assert not f["mono"], f"{where} has monospace text: footers say plain words (ui.js foot())"

    @test(parameters=sorted(KNOWN_TOASTS))
    def test_the_op_guard_sees_the_known_toasts(self, parameter):
        for state in KNOWN_TOASTS[parameter]:
            assert shown(rendered()[parameter][state]["toast"]), (
                f"{parameter}#{state}: the guard found no toast"
            )

    @test(parameters=sorted(KNOWN_FOOTERS))
    def test_the_footer_guard_sees_the_known_footers(self, parameter):
        for state in KNOWN_FOOTERS[parameter]:
            html = rendered()[parameter][state]["html"]
            assert footers(html), f"{parameter}#{state}: the guard found no footer"
