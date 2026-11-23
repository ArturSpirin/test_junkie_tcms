"""Web app structure: views hold no data and fetch nothing; js/data.js is the only way into js/data/."""

import re
from pathlib import Path

from test_junkie.decorators import Suite, test

JS = Path(__file__).parents[2] / "src" / "test_junkie_tcms" / "web" / "js"
VIEWS = sorted((JS / "views").glob("*.js"))
STATIC_IMPORT = re.compile(r'^import\b[^"]*"([^"]+)"', re.M)
DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(")
ANY_IMPORT = re.compile(r"^import\b|\bimport\s*\(", re.M)
NETWORK = re.compile(r"\bfetch\s*\(|XMLHttpRequest|\bWebSocket\s*\(|\bEventSource\s*\(")
STRINGS = re.compile(r'"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`')
TOP_LEVEL_ARRAY = re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*\[", re.M)
OBJECT_KEY = re.compile(r"[{,]\s*(\w+)\s*:")
# A view may keep option lists for fixed enums (what a menu shows for each value): the option fields
# ui.js dd() reads. Any other key is data.
OPTION_KEYS = {"v", "label", "short", "hint", "icon", "dot", "kbd", "group", "dis", "danger"}


def top_level_arrays(src: str):
    """Yield (name, body) for each array literal assigned at module top level."""
    for m in TOP_LEVEL_ARRAY.finditer(src):
        depth, i = 0, m.end() - 1
        for i in range(m.end() - 1, len(src)):
            depth += {"[": 1, "]": -1}.get(src[i], 0)
            if depth == 0:
                break
        yield m.group(1), src[m.end() : i]


@Suite()
class WebStructure:
    @test()
    def test_there_are_sixteen_views(self):
        assert len(VIEWS) == 16, [v.name for v in VIEWS]

    @test(parameters=[v.name for v in VIEWS])
    def test_view_imports_only_ui_shell_and_data(self, parameter):
        src = (JS / "views" / parameter).read_text(encoding="utf-8")
        imports = set(STATIC_IMPORT.findall(src))
        assert imports <= {"../ui.js", "../shell.js", "../data.js"}, imports
        assert not DYNAMIC_IMPORT.search(src), f"{parameter} imports a module at run time"

    @test(parameters=[v.name for v in VIEWS])
    def test_view_holds_no_data_rows(self, parameter):
        src = STRINGS.sub('""', (JS / "views" / parameter).read_text(encoding="utf-8"))
        for name, body in top_level_arrays(src):
            keys = set(OBJECT_KEY.findall(body))
            assert keys <= OPTION_KEYS, f"{parameter}: {name} holds data keys {sorted(keys - OPTION_KEYS)}"

    @test()
    def test_no_module_calls_the_network(self):
        hits = [
            p.relative_to(JS).as_posix()
            for p in JS.rglob("*.js")
            if NETWORK.search(p.read_text(encoding="utf-8"))
        ]
        assert hits == [], hits

    @test()
    def test_only_data_js_reaches_the_data_folder(self):
        hits = [
            p.relative_to(JS).as_posix()
            for p in JS.rglob("*.js")
            if p.name != "data.js" and re.search(r"[\"'`]\.{1,2}/data/", p.read_text(encoding="utf-8"))
        ]
        assert hits == [], hits

    @test()
    def test_menu_button_names_the_nav_it_opens(self):
        src = (JS / "shell.js").read_text(encoding="utf-8")
        burger = re.search(r"<button[^>]*\bdata-nav-toggle\b[^>]*>", src).group(0)
        assert 'aria-expanded="false"' in burger, burger
        controls = re.search(r'aria-controls="([^"]+)"', burger).group(1)
        assert re.search(rf'<nav\b[^>]*\bid="{controls}"', src), f"no nav with id {controls!r}"

    @test()
    def test_only_set_nav_writes_the_nav_open_class(self):
        # the sidebar class and the Menu button's aria-expanded change together, in one place
        writes = re.compile(r"classList\.\w+\(\s*[\"']nav-open[\"']")
        shell = (JS / "shell.js").read_text(encoding="utf-8")
        set_nav = re.search(r"const setNav = \(open\) => \{(.*?)\n  \};", shell, re.S).group(1)
        assert writes.search(set_nav), "setNav no longer writes nav-open"
        hits = []
        for p in JS.rglob("*.js"):
            src = p.read_text(encoding="utf-8").replace(set_nav, "")
            hits += [p.relative_to(JS).as_posix() for _ in writes.finditer(src)]
        assert hits == [], hits

    @test()
    def test_data_modules_import_nothing(self):
        hits = [
            p.name for p in (JS / "data").glob("*.js") if ANY_IMPORT.search(p.read_text(encoding="utf-8"))
        ]
        assert hits == [], hits
