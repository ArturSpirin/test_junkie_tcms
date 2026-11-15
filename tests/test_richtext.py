"""Rich text: the node set, and JSON -> Markdown -> JSON without losing content."""

from test_junkie.decorators import Suite, test

from test_junkie_tcms.richtext import RichTextError, doc_to_md, doc_to_text, md_to_doc, validate
from tests import support

IMG = "attachment:01ARZ3NDEKTSV4RRFFQ69G5FAV"


def t(text, *marks, href=None):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = [{"type": m, "attrs": {"href": href}} if m == "link" else {"type": m} for m in marks]
    return node


def p(*inline):
    return {"type": "paragraph", "content": list(inline)} if inline else {"type": "paragraph"}


def h(level, *inline):
    return {"type": "heading", "attrs": {"level": level}, "content": list(inline)}


def li(*blocks):
    return {"type": "listItem", "content": list(blocks)}


def task(checked, *blocks):
    return {"type": "taskItem", "attrs": {"checked": checked}, "content": list(blocks)}


def bullets(*items):
    return {"type": "bulletList", "content": list(items)}


def ordered(start, *items):
    return {"type": "orderedList", "attrs": {"start": start}, "content": list(items)}


def tasks(*items):
    return {"type": "taskList", "content": list(items)}


def code(text, language=None):
    node = {"type": "codeBlock", "attrs": {"language": language}}
    if text:
        node["content"] = [t(text)]
    return node


def quote(*blocks):
    return {"type": "blockquote", "content": list(blocks)} if blocks else {"type": "blockquote"}


def table(header, *rows):
    def row(kind, cells):
        return {"type": "tableRow", "content": [{"type": kind, "content": [p(*c)]} for c in cells]}

    return {"type": "table", "content": [row("tableHeader", header), *(row("tableCell", r) for r in rows)]}


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


BR = {"type": "hardBreak"}
HR = {"type": "horizontalRule"}
CELL = {"type": "tableCell"}


def image(alt=""):
    return {"type": "image", "attrs": {"src": IMG, "alt": alt}}


# Every node and mark, and the escaping edge cases, each already in normalized form.
CORPUS = {
    "paragraph": doc(p(t("Plain text."))),
    "headings": doc(h(1, t("One")), h(2, t("Two")), h(3, t("Three"))),
    "marks": doc(
        p(
            t("a "),
            t("bold", "bold"),
            t(" "),
            t("italic", "italic"),
            t(" "),
            t("strike", "strike"),
            t(" "),
            t("code", "code"),
            t(" "),
            t("link", "link", href="https://example.com/a"),
            t("."),
        )
    ),
    "nested_marks": doc(
        p(t("x", "bold"), t("y", "bold", "italic"), t("z", "bold")),
        p(t("all", "bold", "italic", "strike")),
    ),
    "link_with_marks": doc(
        p(
            t("see ", "link", href="https://example.com/x_(y)?q=a%20b"),
            t("this", "link", "bold", href="https://example.com/x_(y)?q=a%20b"),
        )
    ),
    "code_marks": doc(p(t("``a`b``", "code"), t(" "), t(" sp ", "code"), t(" "), t("x", "bold", "code"))),
    "hard_breaks": doc(p(t("one"), BR, t("two"), BR, t("  indented"), BR, t("trailing  "), BR, t("end"))),
    "image": doc(p(t("see "), image("a [screenshot] *here*"), t(" after"))),
    "image_alone": doc(p(image())),
    "bang_before_link": doc(p(t("wow!"), t("link", "link", href="https://example.com"))),
    "escapes": doc(
        p(t("a * b _ c ` d [e] <f> & g ~ h | i \\ j # k ! l")),
        p(t("# not a heading")),
        p(t("> not a quote")),
        p(t("- not a list")),
        p(t("+ not a list")),
        p(t("1. not a list")),
        p(t("2) not a list")),
        p(t("---")),
        p(t("===")),
        p(t("    not code")),
        p(t("&amp; entity &#32; text")),
        p(t("<b>raw html</b>")),
        p(t("tab\tinside")),
    ),
    "setext_after_break": doc(p(t("title"), BR, t("==="), BR, t("---"))),
    "heading_escapes": doc(h(2, t("Ends with #")), h(1, t("  spaced  "))),
    "bullets": doc(bullets(li(p(t("one"))), li(p(t("two")), p(t("second para"))), li(p(t("three"))))),
    "nested_lists": doc(
        bullets(
            li(p(t("parent")), bullets(li(p(t("child"))), li(p(t("child 2")))), ordered(1, li(p(t("n1"))))),
            li(p(t("next"))),
        )
    ),
    "ordered_start": doc(ordered(3, li(p(t("three"))), li(p(t("four"))))),
    "ordered_nested_start": doc(ordered(9, li(p(t("nine")), ordered(5, li(p(t("five"))))), li(p(t("ten"))))),
    "ordered_zero": doc(ordered(0, li(p(t("zero"))))),
    "adjacent_lists": doc(
        bullets(li(p(t("a")))), bullets(li(p(t("b")))), ordered(1, li(p(t("c")))), ordered(1, li(p(t("d"))))
    ),
    "bullet_then_tasks": doc(bullets(li(p(t("a")))), tasks(task(False, p(t("b"))))),
    "tasks": doc(tasks(task(False, p(t("todo"))), task(True, p(t("done"), BR, t("more"))))),
    "task_with_nested": doc(tasks(task(True, p(t("parent")), tasks(task(False, p(t("child"))))))),
    "box_as_text": doc(bullets(li(p(t("[ ] not a task"))))),
    "empty_first_paragraph": doc(bullets(li(p(), bullets(li(p(t("only child"))))), li(p(), HR))),
    "list_item_blocks": doc(
        bullets(li(p(t("intro")), code("x = 1\n\ny = 2", "python"), quote(p(t("q"))), h(2, t("head"))))
    ),
    "code": doc(code("def f():\n    return 1", "python"), code("plain"), code("")),
    "code_fences": doc(code("```\ninner\n```", "md"), code("ends with blank\n")),
    "blockquote": doc(quote(p(t("quoted")), bullets(li(p(t("in quote")))), quote(p(t("deeper"))))),
    "empty_quote": doc(quote()),
    "adjacent_quotes": doc(quote(p(t("a"))), quote(p(t("b")))),
    "hr": doc(p(t("above")), HR, p(t("below")), HR, HR),
    "table": doc(
        table(
            [[t("Name")], [t("Value", "bold")]],
            [[t("a | b")], [t("x|y", "code")]],
            [[], [t("  padded  ")]],
            [[t("back\\slash")], [t("-")]],
        )
    ),
    "one_column_table": doc(table([[t("h")]], [[t("c")]])),
    "adjacent_tables": doc(table([[t("a")]]), table([[t("b")]])),
    "mixed": doc(
        h(1, t("Login")),
        p(t("Steps for "), t("SSO", "bold"), t(":")),
        ordered(1, li(p(t("Open "), t("/login", "code"))), li(p(t("Click "), t("Sign in", "italic")))),
        tasks(task(False, p(t("check logs")))),
        table([[t("Field")], [t("Value")]], [[t("user")], [t("admin@example.com")]]),
        code("curl -X POST", "bash"),
    ),
    "unicode": doc(p(t("Ünïcödé — “quotes” 日本語 🎉"))),
}


@Suite()
class RichText:
    @test(parameters=sorted(CORPUS))
    def test_json_to_markdown_to_json_keeps_everything(self, parameter):
        name = parameter
        original = CORPUS[name]
        assert validate(original) == original, "corpus entries are written in normalized form"
        markdown = doc_to_md(original)
        assert md_to_doc(markdown) == original, markdown
        assert doc_to_md(md_to_doc(markdown)) == markdown

    @test()
    def test_markdown_reads_common_syntax(self):
        got = md_to_doc(
            "Intro *em* __strong__ ~~gone~~ `code` <https://example.com>\nnext line\n\n"
            "* a\n* b\n\n- [x] done\n- [ ] open\n\n##### deep\n\n    indented code\n\n***\n"
        )
        assert got == doc(
            p(
                t("Intro "),
                t("em", "italic"),
                t(" "),
                t("strong", "bold"),
                t(" "),
                t("gone", "strike"),
                t(" "),
                t("code", "code"),
                t(" "),
                t("https://example.com", "link", href="https://example.com"),
                BR,
                t("next line"),
            ),
            bullets(li(p(t("a"))), li(p(t("b")))),
            tasks(task(True, p(t("done"))), task(False, p(t("open")))),
            h(3, t("deep")),
            code("indented code"),
            HR,
        )

    @test()
    def test_mixed_task_and_plain_items_keep_the_box_as_text(self):
        assert md_to_doc("- [x] done\n- plain\n") == doc(bullets(li(p(t("[x] done"))), li(p(t("plain")))))

    @test()
    def test_raw_html_is_text_not_markup(self):
        assert md_to_doc("<script>alert(1)</script>\n\nx <b>y</b>") == doc(
            p(t("<script>alert(1)</script>")), p(t("x <b>y</b>"))
        )

    @test()
    def test_unsafe_links_never_become_links(self):
        assert md_to_doc("[x](javascript:alert(1))") == doc(p(t("[x](javascript:alert(1))")))
        with support.raises(RichTextError, match="http, https or mailto"):
            md_to_doc("[x](ftp://example.com)")

    @test()
    def test_images_must_be_attachments(self):
        with support.raises(RichTextError, match="attachment"):
            md_to_doc("![x](https://example.com/a.png)")

    @test(
        parameters=[
            ({"type": "paragraph"}, "root must be a doc"),
            (doc({"type": "video"}), "unknown node"),
            (doc(p(t("x", "underline"))), "unknown mark"),
            (doc(p(t("a\nb"))), "hardBreak"),
            (doc(h(4, t("x"))), "level"),
            (doc(h(1, t("a"), BR, t("b"))), "can't be inside heading"),
            (doc(p({"type": "text", "text": "x", "marks": [{"type": "bold"}, {"type": "bold"}]})), "twice"),
            (doc(p(t("x", "link", href="javascript:alert(1)"))), "http, https or mailto"),
            (doc(p({"type": "image", "attrs": {"src": "https://example.com/x.png"}})), "attachment"),
            (doc(code("x", "no spaces allowed")), "language"),
            (doc(bullets()), "at least one"),
            (doc(bullets(p(t("x")))), "can't be inside bulletList"),
            (doc({"type": "paragraph", "attrs": {"align": "left"}}), "unknown attrs"),
            (doc(table([[t("a")], [t("b")]], [[t("c")]])), "same number"),
            (doc({"type": "table", "content": [{"type": "tableRow", "content": [CELL]}]}), "tableHeader"),
            (doc(table([[t("a"), BR, t("b")]])), "line break"),
        ]
    )
    def test_invalid_docs_are_refused(self, parameter):
        bad, message = parameter
        with support.raises(RichTextError, match=message):
            validate(bad)

    @test()
    def test_normalize_merges_and_drops(self):
        messy = doc(
            p(t("a"), t(""), t("b"), BR),
            p(),
            p(t("x", "italic", "bold"), t("y", "bold", "italic")),
            bullets({"type": "listItem"}),
            {"type": "codeBlock", "content": [t("a"), t("b")]},
            p(t("l", "link", href="https://example.com/a b")),
        )
        assert validate(messy) == doc(
            p(t("ab")),
            p(t("xy", "bold", "italic")),
            bullets(li(p())),
            code("ab"),
            p(t("l", "link", href="https://example.com/a%20b")),
        )

    @test()
    def test_tiptap_link_attrs_are_dropped(self):
        tiptap = doc(
            p(
                {
                    "type": "text",
                    "text": "x",
                    "marks": [
                        {"type": "link", "attrs": {"href": "https://e.com", "target": "_blank", "rel": "x"}}
                    ],
                }
            )
        )
        assert validate(tiptap) == doc(p(t("x", "link", href="https://e.com")))

    @test()
    def test_plain_text_for_search(self):
        assert doc_to_text(CORPUS["mixed"]) == (
            "Login\nSteps for SSO:\nOpen /login\nClick Sign in\ncheck logs\n"
            "Field Value\nuser admin@example.com\ncurl -X POST"
        )
