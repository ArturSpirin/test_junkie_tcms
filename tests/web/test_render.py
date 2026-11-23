"""Web app views: every view renders every state of the approved mock from its data module, under node."""

import functools
import json
import re
import shutil
import subprocess
from pathlib import Path

from test_junkie.decorators import Suite, test

HERE = Path(__file__).parent
MOCK_STATES = json.loads((HERE / "mock_states.json").read_text(encoding="utf-8"))
# Leaks of a missing or wrong value into the markup.
SUSPECT = re.compile(r"undefined|NaN|\[object |null<")


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
