"""The `md-bundle` format (T6b): a zip of Markdown files, one per case, that imports like the CSV.

A file is JSON front matter (one `name: <JSON value>` line per field, so it reads as YAML too), the
title as the `# ` line, then the rich sections split by boundary marker lines, like MIME multipart:

    ---
    key: "PAY-1"
    ...
    boundary: "tcms-3f9a"
    ---
    # Pay by card

    <!-- tcms-3f9a description -->
    ...Markdown...
    <!-- tcms-3f9a preconditions -->
    ...Markdown...
    <!-- tcms-3f9a step 01J... action -->
    ...Markdown...

The boundary is lengthened until it appears nowhere in the case's text, so content can't split a section.
A file parses into a row in the CSV's `COLUMNS` shape, which then takes the CSV import's one write path.
"""

import base64
import binascii
import hashlib
import io
import json
import re
import zipfile
import zlib
from typing import Any

from fastapi import HTTPException

MAX_UNCOMPRESSED = 20 * 1024 * 1024
MAX_ENTRIES = 5000
FRONT = (
    "key",
    "version",
    "feature",
    "priority",
    "type",
    "status",
    "automation",
    "automation_ref",
    "tags",
    "links",
    "custom",
)
STRINGS = {"key", "feature", "priority", "type", "status", "automation", "automation_ref", "boundary"}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
_DRIVE = re.compile(r"^[A-Za-z]:")


class FileError(Exception):
    def __init__(self, column: str | None, detail: str):
        self.column, self.detail = column, detail


def _boundary(text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    n = 4
    while f"tcms-{digest[:n]}" in text:
        n += 1
        if n > len(digest):
            digest += hashlib.sha256(digest.encode()).hexdigest()
    return f"tcms-{digest[:n]}"


def case_to_md(case: dict[str, Any]) -> str:
    """One case (the export's row, with JSON fields as values) as a bundle file."""
    sections = [("description", case["description"]), ("preconditions", case["preconditions"])]
    for s in case["steps"]:
        sections += [(f"step {s['id']} action", s["action"]), (f"step {s['id']} expected", s["expected"])]
    boundary = _boundary(case["title"] + "\n" + "\n".join(md for _, md in sections))
    front = [
        f"{name}: {json.dumps(case[name], ensure_ascii=False, sort_keys=name == 'custom')}" for name in FRONT
    ]
    front.append(f"boundary: {json.dumps(boundary)}")
    body = "".join(f"<!-- {boundary} {name} -->\n{md}\n" for name, md in sections)
    return "---\n" + "\n".join(front) + "\n---\n# " + case["title"] + "\n\n" + body


def _front(lines: list[str]) -> tuple[dict[str, Any], int]:
    if not lines or lines[0] != "---":
        raise FileError(None, "must start with a --- front matter line")
    values: dict[str, Any] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line == "---":
            return values, i + 1
        name, sep, raw = line.partition(":")
        name = name.strip()
        if not sep or name not in (*FRONT, "boundary"):
            raise FileError(None, f"unknown front matter line: {line[:80]!r}")
        if name in values:
            raise FileError(name, "appears twice in the front matter")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as e:
            raise FileError(name, f"not JSON: {e.msg}") from e
        if name in STRINGS and value is not None and not isinstance(value, str):
            raise FileError(name, "must be a JSON string")
        if (
            name == "version"
            and value is not None
            and (isinstance(value, bool) or not isinstance(value, int))
        ):
            raise FileError(name, "must be a whole number")
        values[name] = value
    raise FileError(None, "the front matter has no closing --- line")


def md_to_row(text: str) -> dict[str, str]:
    """A bundle file as a row in the CSV's `COLUMNS` shape (strings, JSON columns as JSON text)."""
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    values, i = _front(lines)
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i == len(lines) or not lines[i].startswith("# "):
        raise FileError("title", "needs a '# ' title line after the front matter")
    title = lines[i][2:]
    boundary = values.get("boundary")
    marker = re.compile(rf"^<!-- {re.escape(boundary)} (.+) -->$") if boundary else None
    pre: dict[str, str] = {}
    steps: list[dict[str, Any]] = []
    sections: list[tuple[dict, str, list[str]]] = []
    for line in lines[i + 1 :]:
        m = marker.match(line) if marker else None
        if not m:
            if not sections:
                if line.strip():
                    raise FileError(None, "text outside a section (sections start with the boundary line)")
                continue
            sections[-1][2].append(line)
            continue
        name = m.group(1).split(" ")
        if name in (["description"], ["preconditions"]):
            part = name[0]
            if part in pre:
                raise FileError(part, "appears twice")
            holder = pre
        elif len(name) in (2, 3) and name[0] == "step" and name[-1] in ("action", "expected"):
            part, step_id = name[-1], (name[1] if len(name) == 3 else None)
            last = steps[-1] if steps else None
            if part == "action" or last is None or part in last or last.get("id") != step_id:
                steps.append({"id": step_id} if step_id else {})
            holder = steps[-1]
        else:
            raise FileError(None, f"unknown section {m.group(1)!r}")
        holder[part] = ""
        sections.append((holder, part, []))
    for holder, part, body in sections:
        holder[part] = "\n".join(body)
    preconditions = pre.get("preconditions")

    def text_of(name: str) -> str:
        value = values.get(name)
        return "" if value is None else str(value)

    def json_of(name: str) -> str:
        value = values.get(name)
        return "" if value is None else json.dumps(value, ensure_ascii=False)

    # A file with no description section (one exported before cases had it) leaves the key out of the row,
    # so the import keeps the stored description instead of clearing it.
    described = {"description": pre["description"]} if "description" in pre else {}
    return {
        "key": text_of("key"),
        "version": text_of("version"),
        "feature": text_of("feature"),
        "title": title,
        **described,
        "preconditions": preconditions or "",
        "steps": json.dumps(steps, ensure_ascii=False),
        "priority": text_of("priority"),
        "type": text_of("type"),
        "status": text_of("status"),
        "automation": text_of("automation"),
        "automation_ref": text_of("automation_ref"),
        "tags": json_of("tags"),
        "links": json_of("links"),
        "custom": json_of("custom"),
    }


def write_bundle(cases: list[dict[str, Any]]) -> bytes:
    """The zip: `<KEY>.md` per case at the root. Fixed timestamps, so the same cases give the same bytes."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for case in cases:
            zf.writestr(
                zipfile.ZipInfo(f"{case['key']}.md", FIXED_TIME), case_to_md(case), zipfile.ZIP_DEFLATED
            )
    return out.getvalue()


def read_bundle(encoded: str, max_bytes: int) -> list[tuple[str, bytes]]:
    """The `.md` entries of a base64 zip, by name. Size caps are 413 and a bad zip is 422, checked from the
    zip directory before anything is read."""
    if len(encoded) > (max_bytes + 2) // 3 * 4 + 4:
        raise HTTPException(413, "bundle is over 5 MB")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(422, "bundle is not base64") from e
    if len(raw) > max_bytes:
        raise HTTPException(413, "bundle is over 5 MB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise HTTPException(422, "bundle is not a zip") from e
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise HTTPException(413, f"bundle has over {MAX_ENTRIES} entries")
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED:
            raise HTTPException(413, "bundle is over 20 MB uncompressed")
        bad = sorted(
            info.filename
            for info in infos
            if info.filename.startswith(("/", "\\"))
            or _DRIVE.match(info.filename)
            or ".." in re.split(r"[/\\]", info.filename)
        )
        if bad:
            raise HTTPException(422, f"bundle has unsafe file names: {', '.join(bad)}")
        files = [
            info
            for info in infos
            if not info.is_dir()
            and not info.filename.startswith("__MACOSX/")
            and info.filename.lower().endswith(".md")
        ]
        try:
            return [(info.filename, zf.read(info)) for info in sorted(files, key=lambda f: f.filename)]
        except (zipfile.BadZipFile, zlib.error, NotImplementedError, OSError, EOFError) as e:
            raise HTTPException(422, f"bundle is not a valid zip: {e}") from e
