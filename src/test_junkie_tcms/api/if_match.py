"""`If-Match` on case edits: the version the client last read. Missing is 428 (errors.py), stale is 409."""

from fastapi import Header, HTTPException

from test_junkie_tcms.errors import ProblemError


def parse_version(value: str) -> int:
    """`3`, `"3"` and `W/"3"` all mean version 3; anything else is 422."""
    raw = value.strip()
    if raw.startswith("W/"):
        raw = raw[2:]
    raw = raw.strip('"')
    if not raw.isdigit():
        raise HTTPException(422, 'If-Match must be a case version number, e.g. 3 or "3"')
    return int(raw)


def if_match(
    value: str = Header(
        alias="If-Match",
        description='The case version you last read (its ETag): 3, "3" or W/"3". A stale one gets 409',
    ),
) -> int:
    return parse_version(value)


def stale(current_version: int) -> ProblemError:
    return ProblemError(
        409,
        f"The case changed: it is at version {current_version}. Read it again and retry",
        headers={"ETag": f'"{current_version}"'},
        current_version=current_version,
    )
