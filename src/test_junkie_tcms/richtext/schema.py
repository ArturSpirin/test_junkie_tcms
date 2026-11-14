"""The rich text node set (PLAN-27 §3, TASK-3277 plan §5): validate and normalize a ProseMirror JSON doc.

Names match TipTap's StarterKit so the web UI needs no mapping. Everything a doc can hold also has a
Markdown form, so `doc_to_md` and `md_to_doc` round-trip a normalized doc.
"""

import re
from typing import Any

from markdown_it import MarkdownIt

BLOCKS = frozenset(
    {
        "paragraph",
        "heading",
        "bulletList",
        "orderedList",
        "taskList",
        "codeBlock",
        "blockquote",
        "table",
        "horizontalRule",
    }
)
INLINES = frozenset({"text", "hardBreak", "image"})
TEXTBLOCKS = frozenset({"paragraph", "heading"})

CHILDREN: dict[str, frozenset[str]] = {
    "doc": BLOCKS,
    "blockquote": BLOCKS,
    "listItem": BLOCKS,
    "taskItem": BLOCKS,
    "paragraph": INLINES,
    "heading": INLINES - {"hardBreak"},
    "bulletList": frozenset({"listItem"}),
    "orderedList": frozenset({"listItem"}),
    "taskList": frozenset({"taskItem"}),
    "codeBlock": frozenset({"text"}),
    "table": frozenset({"tableRow"}),
    "tableRow": frozenset({"tableHeader", "tableCell"}),
    "tableHeader": frozenset({"paragraph"}),
    "tableCell": frozenset({"paragraph"}),
    "horizontalRule": frozenset(),
    "text": frozenset(),
    "hardBreak": frozenset(),
    "image": frozenset(),
}

# Outermost first. Marks are sorted into this order, so equal docs compare equal.
MARK_ORDER = ("link", "bold", "italic", "strike", "code")
LINK_SCHEMES = ("http:", "https:", "mailto:")
IMAGE_SRC = re.compile(r"^attachment:[0-9A-HJKMNP-TV-Z]{26}$")
LANGUAGE = re.compile(r"^[A-Za-z0-9_+#.-]{0,40}$")
# TipTap's link extension adds these; they carry nothing a Markdown link can hold, so they are dropped.
LINK_UI_ATTRS = frozenset({"target", "rel", "class"})

_md_links = MarkdownIt("commonmark")


class RichTextError(ValueError):
    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def empty_doc() -> dict:
    return {"type": "doc", "content": []}


def normalize_href(href: str) -> str:
    """The same percent-encoding markdown-it applies on the way in, so hrefs round-trip unchanged."""
    return _md_links.normalizeLink(href)


def _attrs(node: dict, path: str, allowed: dict[str, Any]) -> dict:
    attrs = node.get("attrs") or {}
    if not isinstance(attrs, dict):
        raise RichTextError(path, "attrs must be an object")
    unknown = set(attrs) - set(allowed)
    if unknown:
        raise RichTextError(path, f"unknown attrs: {', '.join(sorted(unknown))}")
    return {key: attrs.get(key, default) for key, default in allowed.items()}


def _node_attrs(kind: str, node: dict, path: str) -> dict | None:
    if kind == "heading":
        attrs = _attrs(node, path, {"level": 1})
        if attrs["level"] not in (1, 2, 3) or isinstance(attrs["level"], bool):
            raise RichTextError(path, "heading level must be 1, 2 or 3")
        return attrs
    if kind == "orderedList":
        attrs = _attrs(node, path, {"start": 1})
        start = attrs["start"]
        if not isinstance(start, int) or isinstance(start, bool) or not 0 <= start <= 999_999_999:
            raise RichTextError(path, "orderedList start must be an integer from 0 to 999999999")
        return attrs
    if kind == "taskItem":
        attrs = _attrs(node, path, {"checked": False})
        if not isinstance(attrs["checked"], bool):
            raise RichTextError(path, "taskItem checked must be true or false")
        return attrs
    if kind == "codeBlock":
        attrs = _attrs(node, path, {"language": None})
        language = attrs["language"] or None
        if language is not None and (not isinstance(language, str) or not LANGUAGE.match(language)):
            raise RichTextError(path, "codeBlock language must be a short word, like python")
        return {"language": language}
    if kind == "image":
        attrs = _attrs(node, path, {"src": None, "alt": "", "title": None})
        if not isinstance(attrs["src"], str) or not IMAGE_SRC.match(attrs["src"]):
            raise RichTextError(path, "image src must be attachment:<ULID>")
        alt = attrs["alt"] or ""
        if not isinstance(alt, str) or "\n" in alt:
            raise RichTextError(path, "image alt must be one line of text")
        return {"src": attrs["src"], "alt": alt}
    if node.get("attrs"):
        _attrs(node, path, {})
    return None


def _marks(node: dict, path: str) -> list[dict]:
    raw = node.get("marks") or []
    if not isinstance(raw, list):
        raise RichTextError(path, "marks must be a list")
    marks: dict[str, dict] = {}
    for i, mark in enumerate(raw):
        mpath = f"{path}.marks[{i}]"
        kind = mark.get("type") if isinstance(mark, dict) else None
        if kind not in MARK_ORDER:
            raise RichTextError(mpath, f"unknown mark {kind!r}")
        if kind in marks:
            raise RichTextError(mpath, f"mark {kind} appears twice")
        if kind == "link":
            attrs = _attrs(mark, mpath, {"href": None, "title": None} | dict.fromkeys(LINK_UI_ATTRS))
            href = attrs["href"]
            if not isinstance(href, str) or not href.lower().startswith(LINK_SCHEMES):
                raise RichTextError(mpath, "link href must be an http, https or mailto URL")
            marks[kind] = {"type": "link", "attrs": {"href": normalize_href(href)}}
        else:
            if mark.get("attrs"):
                _attrs(mark, mpath, {})
            marks[kind] = {"type": kind}
    return [marks[k] for k in MARK_ORDER if k in marks]


def _inline(content: list[dict]) -> list[dict]:
    """Merge neighbouring text with the same marks, drop empty text and trailing line breaks."""
    out: list[dict] = []
    for node in content:
        if node["type"] == "text":
            if not node["text"]:
                continue
            if out and out[-1]["type"] == "text" and out[-1].get("marks") == node.get("marks"):
                out[-1] = {**out[-1], "text": out[-1]["text"] + node["text"]}
                continue
        out.append(node)
    while out and out[-1]["type"] == "hardBreak":
        out.pop()
    return out


def _is_empty_paragraph(node: dict) -> bool:
    return node["type"] == "paragraph" and not node.get("content")


def _walk(node: Any, path: str, parent: str) -> dict:
    if not isinstance(node, dict):
        raise RichTextError(path, "a node must be an object")
    kind = node.get("type")
    if kind not in CHILDREN or kind == "doc":
        raise RichTextError(path, f"unknown node {kind!r}")
    if kind not in CHILDREN[parent]:
        raise RichTextError(path, f"{kind} can't be inside {parent}")
    out: dict[str, Any] = {"type": kind}
    attrs = _node_attrs(kind, node, path)
    if attrs is not None:
        out["attrs"] = attrs

    if kind == "text":
        text = node.get("text")
        if not isinstance(text, str):
            raise RichTextError(path, "text must be a string")
        if parent == "codeBlock":
            if node.get("marks"):
                raise RichTextError(path, "text in a codeBlock can't have marks")
        elif "\n" in text or "\r" in text:
            raise RichTextError(path, "use a hardBreak node for a line break")
        out["text"] = text
        marks = _marks(node, path) if parent != "codeBlock" else []
        if marks:
            out["marks"] = marks
        return out
    if node.get("marks"):
        raise RichTextError(path, f"{kind} can't have marks")

    raw = node.get("content") or []
    if not isinstance(raw, list):
        raise RichTextError(path, "content must be a list")
    if not CHILDREN[kind] and raw:
        raise RichTextError(path, f"{kind} has no content")
    content = [_walk(child, f"{path}.content[{i}]", kind) for i, child in enumerate(raw)]

    if kind in TEXTBLOCKS:
        content = _inline(content)
        if parent in ("tableHeader", "tableCell") and any(c["type"] == "hardBreak" for c in content):
            raise RichTextError(path, "a table cell can't hold a line break")
    elif kind == "codeBlock":
        content = [{"type": "text", "text": "".join(c["text"] for c in content)}] if content else []
        content = [c for c in content if c["text"]]
    elif kind in ("blockquote",):
        content = [c for c in content if not _is_empty_paragraph(c)]
    elif kind in ("listItem", "taskItem"):
        if not content or content[0]["type"] != "paragraph":
            content = [{"type": "paragraph"}, *content]
        content = [content[0], *(c for c in content[1:] if not _is_empty_paragraph(c))]
    elif kind in ("bulletList", "orderedList", "taskList", "tableRow", "table"):
        if not content:
            raise RichTextError(path, f"{kind} needs at least one child")
    elif kind in ("tableHeader", "tableCell"):
        if len(content) > 1:
            raise RichTextError(path, "a table cell holds one paragraph (a Markdown table can't hold more)")
        if not content:
            content = [{"type": "paragraph"}]

    if kind == "table":
        width = len(content[0]["content"])
        for r, row in enumerate(content):
            cells = {c["type"] for c in row["content"]}
            want = "tableHeader" if r == 0 else "tableCell"
            if cells != {want}:
                raise RichTextError(f"{path}.content[{r}]", f"row {r} must hold only {want} cells")
            if len(row["content"]) != width:
                raise RichTextError(f"{path}.content[{r}]", "every row needs the same number of cells")

    if content:
        out["content"] = content
    return out


def validate(doc: Any) -> dict:
    """Check a doc against the node set and return its normalized form. Raises RichTextError."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise RichTextError("$", "the root must be a doc node")
    if doc.get("attrs") or doc.get("marks"):
        raise RichTextError("$", "doc has no attrs or marks")
    raw = doc.get("content") or []
    if not isinstance(raw, list):
        raise RichTextError("$", "content must be a list")
    content = [_walk(child, f"$.content[{i}]", "doc") for i, child in enumerate(raw)]
    return {"type": "doc", "content": [c for c in content if not _is_empty_paragraph(c)]}


def doc_to_text(doc: dict) -> str:
    """Plain text for search: blocks on their own lines, table cells split by spaces."""
    lines: list[str] = []

    def inline(node: dict) -> str:
        parts = []
        for child in node.get("content") or []:
            if child["type"] == "text":
                parts.append(child["text"])
            elif child["type"] == "hardBreak":
                parts.append("\n")
            elif child["type"] == "image":
                parts.append(child["attrs"]["alt"])
        return "".join(parts)

    def walk(node: dict) -> None:
        kind = node["type"]
        if kind in TEXTBLOCKS:
            lines.append(inline(node))
        elif kind == "codeBlock":
            lines.append("".join(c["text"] for c in node.get("content") or []))
        elif kind == "tableRow":
            lines.append(" ".join(inline(cell["content"][0]) for cell in node["content"]))
        else:
            for child in node.get("content") or []:
                walk(child)

    walk(doc)
    return "\n".join(line for line in lines if line)
