"""Markdown in and out of the rich text node set (TASK-3277 plan §5).

`md_to_doc` parses CommonMark plus GFM tables, strikethrough and task lists, and returns a validated doc.
`doc_to_md` writes Markdown that `md_to_doc` reads back to the same doc. Raw HTML is never rendered: it
arrives as text.
"""

import re

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.tasklists import tasklists_plugin

from .schema import LANGUAGE, validate

_parser = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"]).use(tasklists_plugin)

_PUSH = {
    "paragraph_open": "paragraph",
    "heading_open": "heading",
    "bullet_list_open": "bulletList",
    "ordered_list_open": "orderedList",
    "list_item_open": "listItem",
    "blockquote_open": "blockquote",
    "table_open": "table",
    "tr_open": "tableRow",
    "th_open": "tableHeader",
    "td_open": "tableCell",
}
_POP = {name.replace("_open", "_close") for name in _PUSH}
_INLINE_MARKS = {"em": "italic", "strong": "bold", "s": "strike", "link": "link"}


# --- Markdown -> doc -------------------------------------------------------------------------------------


def md_to_doc(source: str) -> dict:
    """Parse Markdown into a normalized doc. Raises RichTextError when the result breaks the node set."""
    root: dict = {"type": "doc", "content": []}
    stack = [root]
    for token in _parser.parse(source):
        if token.type in _PUSH:
            node: dict = {"type": _PUSH[token.type], "content": []}
            if token.type == "heading_open":
                node["attrs"] = {"level": min(int(token.tag[1]), 3)}
            elif token.type == "ordered_list_open":
                start = token.attrGet("start")
                node["attrs"] = {"start": 1 if start is None else int(start)}
            elif token.type == "list_item_open":
                node["task"] = "task-list-item" in str(token.attrGet("class") or "")
            stack[-1]["content"].append(node)
            stack.append(node)
        elif token.type in _POP:
            node = stack.pop()
            if node["type"] == "bulletList":
                _tasks(node)
        elif token.type in ("fence", "code_block"):
            language = token.info.strip().split(" ")[0] if token.type == "fence" else ""
            text = token.content[:-1] if token.content.endswith("\n") else token.content
            stack[-1]["content"].append(
                {
                    "type": "codeBlock",
                    "attrs": {"language": language if LANGUAGE.match(language) else None},
                    "content": [{"type": "text", "text": text}],
                }
            )
        elif token.type == "hr":
            stack[-1]["content"].append({"type": "horizontalRule"})
        elif token.type == "inline":
            parent = stack[-1]
            if parent["type"] in ("tableHeader", "tableCell"):
                paragraph = {"type": "paragraph", "content": []}
                parent["content"].append(paragraph)
                parent = paragraph
            parent["content"].extend(_inline_nodes(token, stack))
    return validate(root)


def _inline_nodes(token: Token, stack: list[dict]) -> list[dict]:
    item = stack[-2] if len(stack) > 1 and stack[-2]["type"] == "listItem" else None
    first_in_item = item is not None and item["content"] and item["content"][0] is stack[-1]
    out: list[dict] = []
    marks: list[dict] = []
    strip_space = False
    for child in token.children or []:
        kind = child.type
        if kind == "text" or kind == "html_inline":
            text = child.content
            box = kind == "html_inline" and "checkbox" in text and not out
            if box and first_in_item and item.get("task"):
                item["checked"] = 'checked="checked"' in text
                strip_space = True
                continue
            if strip_space:
                text, strip_space = text.removeprefix(" "), False
            out.append(_text(text, marks))
        elif kind == "code_inline":
            out.append(_text(child.content, [*marks, {"type": "code"}]))
        elif kind in ("softbreak", "hardbreak"):
            out.append({"type": "hardBreak"})
        elif kind == "image":
            alt = "".join(c.content for c in child.children or [] if c.type in ("text", "code_inline"))
            out.append({"type": "image", "attrs": {"src": child.attrGet("src"), "alt": alt}})
        elif kind.endswith("_open") and kind[:-5] in _INLINE_MARKS:
            mark: dict = {"type": _INLINE_MARKS[kind[:-5]]}
            if mark["type"] == "link":
                mark["attrs"] = {"href": child.attrGet("href")}
            marks.append(mark)
        elif kind.endswith("_close") and kind[:-6] in _INLINE_MARKS:
            name = _INLINE_MARKS[kind[:-6]]
            for i in range(len(marks) - 1, -1, -1):
                if marks[i]["type"] == name:
                    del marks[i]
                    break
    return out


def _text(text: str, marks: list[dict]) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = [dict(m) for m in marks]
    return node


def _tasks(bullet_list: dict) -> None:
    """A bullet list whose items are all `[ ]`/`[x]` items is a task list; otherwise the boxes stay text."""
    items = bullet_list["content"]
    if items and all(item.get("task") and "checked" in item for item in items):
        bullet_list["type"] = "taskList"
        for item in items:
            item["type"] = "taskItem"
            item["attrs"] = {"checked": item["checked"]}
        return
    for item in items:
        if "checked" in item:
            box = "[x] " if item["checked"] else "[ ] "
            item["content"][0]["content"].insert(0, {"type": "text", "text": box})


# --- doc -> Markdown -------------------------------------------------------------------------------------

_ALWAYS = frozenset("\\*_`[]<&~|")
_BLOCK_START = frozenset("#>+=-")
_ORDERED_START = re.compile(r"^\d+(?=[.)])")
_WRAP_OPEN = {"bold": "**", "italic": "*", "strike": "~~", "link": "["}


def doc_to_md(doc: dict) -> str:
    """Markdown for a validated doc. `md_to_doc(doc_to_md(doc)) == doc` for every normalized doc, except
    for whitespace at the edge of a bold, italic or strike run in mid-line and empty task items."""
    return _blocks(doc.get("content") or [], in_item=False)


def _list_kind(node: dict) -> str | None:
    kind = node["type"]
    if kind in ("bulletList", "taskList"):
        return "bullet"
    return "ordered" if kind == "orderedList" else None


def _blocks(nodes: list[dict], in_item: bool) -> str:
    out = ""
    prev: dict | None = None
    prev_kind: str | None = None
    alt = 0
    for i, node in enumerate(nodes):
        kind = _list_kind(node)
        alt = alt ^ 1 if kind and kind == prev_kind else 0
        text = _block(node, alt)
        if prev is None:
            out = text
        else:
            sep = "\n\n"
            if in_item and prev["type"] == "paragraph":
                # A nested list (or anything after an empty first paragraph) sits right under the item's line.
                tight_list = kind == "bullet" or (kind == "ordered" and node["attrs"]["start"] == 1)
                if tight_list or (i == 1 and not prev.get("content")):
                    sep = "\n"
            out += sep + text
        prev, prev_kind = node, kind
    return out


def _block(node: dict, alt: int) -> str:
    kind = node["type"]
    content = node.get("content") or []
    if kind == "paragraph":
        return _inline(content)
    if kind == "heading":
        hashes = "#" * node["attrs"]["level"]
        text = _inline(content, heading=True)
        return f"{hashes} {text}" if text else hashes
    if kind == "horizontalRule":
        return "---"
    if kind == "codeBlock":
        text = content[0]["text"] if content else ""
        runs = [len(r) for r in re.findall(r"`+", text)]
        fence = "`" * max(3, max(runs, default=0) + 1)
        body = f"{text}\n" if text else ""
        return f"{fence}{node['attrs']['language'] or ''}\n{body}{fence}"
    if kind == "blockquote":
        inner = _blocks(content, in_item=False)
        return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))
    if kind == "table":
        rows = []
        for r, row in enumerate(content):
            cells = [_inline(cell["content"][0].get("content") or [], cell=True) for cell in row["content"]]
            rows.append("| " + " | ".join(cells) + " |")
            if r == 0:
                rows.append("| " + " | ".join("---" for _ in cells) + " |")
        return "\n".join(rows)
    return _list(node, alt)


def _list(node: dict, alt: int) -> str:
    kind = node["type"]
    items = []
    for i, item in enumerate(node["content"]):
        if kind == "orderedList":
            marker = f"{node['attrs']['start'] + i}{')' if alt else '.'}"
        else:
            marker = "*" if alt else "-"
        indent = " " * (len(marker) + 1)
        head = marker
        if kind == "taskList":
            head += " [x]" if item["attrs"]["checked"] else " [ ]"
        lines = _blocks(item.get("content") or [], in_item=True).split("\n")
        first = f"{head} {lines[0]}" if lines[0] else head
        items.append("\n".join([first, *(indent + line if line else "" for line in lines[1:])]))
    return "\n".join(items)


def _inline(nodes: list[dict], heading: bool = False, cell: bool = False) -> str:
    out: list[str] = []
    stack: list[dict] = []
    line_start = True

    def close(keep: int) -> None:
        while len(stack) > keep:
            mark = stack.pop()
            if mark["type"] == "link":
                href = mark["attrs"]["href"].replace("(", "\\(").replace(")", "\\)")
                out.append(f"]({href})")
            else:
                out.append(_WRAP_OPEN[mark["type"]])

    for i, node in enumerate(nodes):
        kind = node["type"]
        if kind == "hardBreak":
            close(0)
            out.append("\\\n")
            line_start = True
            continue
        if kind == "image":
            close(0)
            alt = _escape(node["attrs"]["alt"], cell=cell)
            out.append(f"![{alt}]({node['attrs']['src']})")
            line_start = False
            continue
        marks = node.get("marks") or []
        code = any(m["type"] == "code" for m in marks)
        wrap = [m for m in marks if m["type"] != "code"]
        keep = 0
        while keep < len(stack) and stack[keep] in wrap:
            keep += 1
        close(keep)
        for mark in wrap:
            if mark not in stack:
                stack.append(mark)
                out.append(_WRAP_OPEN[mark["type"]])
                line_start = False
        nxt = nodes[i + 1] if i + 1 < len(nodes) else None
        line_end = nxt is None or nxt["type"] == "hardBreak"
        if code:
            out.append(_code_span(node["text"], cell))
        else:
            out.append(
                _escape(node["text"], heading=heading, cell=cell, line_start=line_start, line_end=line_end)
            )
        line_start = False
    close(0)
    return "".join(out)


def _escape(
    text: str, heading: bool = False, cell: bool = False, line_start: bool = False, line_end: bool = False
) -> str:
    lead = trail = ""
    if line_start:
        body = text.lstrip(" \t")
        lead = "".join("&#32;" if c == " " else "&#9;" for c in text[: len(text) - len(body)])
        text = body
    if line_end:
        body = text.rstrip(" \t")
        trail = "".join("&#32;" if c == " " else "&#9;" for c in text[len(body) :])
        text = body
    chars = []
    for i, ch in enumerate(text):
        escape = ch in _ALWAYS or (heading and ch == "#") or (ch == "!" and i == len(text) - 1 and not trail)
        chars.append("\\" + ch if escape else ch)
    body = "".join(chars)
    if line_start and not lead and text and not cell:
        if text[0] in _BLOCK_START and not body.startswith("\\"):
            body = "\\" + body
        elif match := _ORDERED_START.match(text):
            body = body[: match.end()] + "\\" + body[match.end() :]
    return lead + body + trail


def _code_span(text: str, cell: bool) -> str:
    fence = "`" * (max((len(r) for r in re.findall(r"`+", text)), default=0) + 1)
    pad = text[0] == "`" or text[-1] == "`" or (text[0] == " " and text[-1] == " " and bool(text.strip(" ")))
    if cell:
        text = text.replace("|", "\\|")
    space = " " if pad else ""
    return f"{fence}{space}{text}{space}{fence}"
