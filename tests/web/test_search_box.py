"""Web app top-bar search: a labelled input "/" focuses without stealing keys; Enter opens the cases view."""

import functools
import json
import re
import shutil
import subprocess
from pathlib import Path

from test_junkie.decorators import Suite, test

HERE = Path(__file__).parent
IGNORED = {"acted": False, "focused": False, "selected": False, "prevented": False}


@functools.cache
def results() -> dict:
    node = shutil.which("node")
    if node is None:
        raise AssertionError(
            "node is not on PATH: the web search tests need node (no packages) to run "
            "tests/web/search_keys.mjs. Install node; these tests never skip."
        )
    proc = subprocess.run(
        [node, str(HERE / "search_keys.mjs")], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert proc.returncode == 0, f"search_keys.mjs exited {proc.returncode}:\n{proc.stderr}"
    return json.loads(proc.stdout)


def search_form(html: str) -> str:
    m = re.search(r'<form class="search" role="search" data-search>.*?</form>', html, re.S)
    assert m, f"no form[role=search] in the top bar:\n{html[:600]}"
    return m.group(0)


@Suite()
class WebSearchBox:
    @test()
    def test_slash_on_the_page_focuses_search(self):
        assert results()["keys"]["body"] == dict.fromkeys(IGNORED, True)

    @test(parameters=["input", "textarea", "contenteditable"])
    def test_slash_in_another_field_is_left_alone(self, parameter):
        assert results()["keys"][parameter] == IGNORED, parameter

    @test(parameters=["dialog", "ctrl", "meta", "other_key", "hidden"])
    def test_slash_is_ignored(self, parameter):
        # an open dialog, a modifier, another key, or the search hidden at narrow widths: "/" types normally
        assert results()["keys"][parameter] == IGNORED, parameter

    @test()
    def test_search_is_a_labelled_input(self):
        form = search_form(results()["markup"])
        assert re.search(r'<input type="search" name="q" aria-label="Search cases"', form), form
        assert 'value=""' in form, form

    @test()
    def test_search_shows_the_url_query_escaped(self):
        assert 'value="refund &quot;x&quot;"' in search_form(results()["markup_q"])

    @test()
    def test_enter_goes_to_the_cases_view(self):
        href = results()["href"]
        assert href == {"empty": "?view=cases", "spaces": "?view=cases", "amp": "?view=cases&q=a%26b%20c"}, (
            href
        )

    @test()
    def test_the_url_query_reaches_the_cases_data(self):
        assert results()["load_q"] == "refund"
        assert results()["load_no_q"] == "", "with no URL query the state's own q (none) stays"
