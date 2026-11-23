"""Tree drag and drop: the drop target stays the row under the pointer, as nothing a drag shows moves rows."""

import re
from pathlib import Path

from test_junkie.decorators import Suite, test

from tests.web.test_render import MOCK_STATES, rendered

WEB = Path(__file__).parents[2] / "src" / "test_junkie_tcms" / "web"
TREE_JS = (WEB / "js" / "views" / "tree.js").read_text(encoding="utf-8")
VIEWS_CSS = (WEB / "css" / "views.css").read_text(encoding="utf-8")
DRAG_STATES = [s for s in MOCK_STATES["tree"] if s.startswith("drag-")]
CARD_STATES = [s for s in MOCK_STATES["tree"] if 'id="dndbar"' in rendered()["tree"][s]["html"]]

TREE_CARD = re.compile(r'<div id="tcol">(.*?)</div><div id="ccol">', re.S)
BAR = re.compile(r'<div class="dnd-bar[^"]*" id="dndbar"[^>]*>.*?</div>', re.S)
GHOST = re.compile(r'<div class="dghost[^>]*>(?:(?!<div).)*?(?:<div class="gx">.*?</div>)?</div>', re.S)
DRAG_MARKS = re.compile(r"\s(?:drop|ins-b|ins-a|nodrop|dragging)(?=[\s\"])")


def tree_card(state: str) -> str:
    m = TREE_CARD.search(rendered()["tree"][state]["html"])
    assert m, f"tree#{state} has no tree card"
    return m.group(1)


def flow(state: str) -> str:
    """The tree card's in-flow markup: without the drag bar, the ghost row and the row marks a drag adds."""
    return DRAG_MARKS.sub("", GHOST.sub("", BAR.sub("", tree_card(state))))


def rule(selector: str) -> str:
    m = re.search(r':where\(\[data-view="tree"\]\) ' + re.escape(selector) + r" \{([^}]*)\}", VIEWS_CSS)
    assert m, f"views.css has no tree rule for {selector}"
    return m.group(1)


@Suite()
class TreeDragAndDrop:
    @test()
    def test_the_drag_states_exist(self):
        assert DRAG_STATES == ["drag-folder-into-folder", "drag-case-reorder", "drag-invalid"], DRAG_STATES

    @test(parameters=CARD_STATES)
    def test_the_drag_bar_sits_in_the_slot_above_the_tree(self, parameter):
        card = tree_card(parameter)
        assert card.count('id="dndbar"') == 1
        in_slot = re.compile(r'<div class="dnd-slot">.*' + BAR.pattern + r'</div>\s*<ul class="tree"', re.S)
        assert in_slot.search(card), (
            f"tree#{parameter}: #dndbar is not the last child of .dnd-slot above #tree"
        )

    @test(parameters=DRAG_STATES)
    def test_a_drag_adds_nothing_to_the_flow_above_the_rows(self, parameter):
        assert 'id="dndbar" role="status">' in tree_card(parameter), f"tree#{parameter} hides the drag bar"
        assert flow(parameter) == flow("default"), f"tree#{parameter} changes the tree card's flow markup"

    @test()
    def test_the_drag_bar_is_out_of_the_flow_and_lets_the_pointer_through(self):
        slot, bar = rule(".dnd-slot"), rule(".dnd-bar")
        assert "position: relative" in slot, slot
        assert "position: absolute" in bar, bar
        assert "bottom: 0" in bar, bar
        assert "pointer-events: none" in bar, bar
        assert not re.search(r"\bmargin", bar), bar

    @test()
    def test_the_drag_bar_is_opaque_over_the_search_row(self):
        for selector, tint in ((".dnd-bar", "--accent-soft"), (".dnd-bar.bad", "--fail-soft")):
            css = rule(selector)
            assert f"linear-gradient(var({tint}), var({tint})), var(--panel)" in css, f"{selector}: {css}"
        assert "--shadow-sm" not in VIEWS_CSS

    @test()
    def test_drop_resolves_its_target_from_the_element_under_the_pointer(self):
        drop = TREE_JS[TREE_JS.index('addEventListener("drop"') :]
        drop = drop[: drop.index("addEventListener", 1)]
        assert re.search(r"e\.target\.closest\(\s*[\"']#tree \.n\[data-id\][\"']\s*\)", drop), drop
