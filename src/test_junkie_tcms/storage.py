"""Where attachment bytes live. Rows in `attachment` point here by `storage_key`."""

import hashlib
import os
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class TooLarge(Exception):
    pass


@dataclass
class Stored:
    key: str
    sha256: str
    size: int


class Storage(Protocol):
    async def put(self, org_id: str, chunks: AsyncIterator[bytes], max_bytes: int) -> Stored: ...

    def open(self, key: str): ...


class LocalStorage:
    """Content-addressed files under `root/<org_id>/<sha[:2]>/<sha>`.

    The org is in the key, so one org's files are never shared with another's and an org purge
    can drop its folder without counting references across orgs.
    """

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)

    async def put(self, org_id: str, chunks: AsyncIterator[bytes], max_bytes: int) -> Stored:
        tmp_dir = self.root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        fd, tmp = tempfile.mkstemp(dir=tmp_dir)
        try:
            with os.fdopen(fd, "wb") as out:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLarge
                    digest.update(chunk)
                    out.write(chunk)
            sha = digest.hexdigest()
            key = f"{org_id}/{sha[:2]}/{sha}"
            target = self.root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return Stored(key=key, sha256=sha, size=size)

    def open(self, key: str):
        return open(self.root / key, "rb")


async def one_chunk(data: bytes) -> AsyncIterator[bytes]:
    yield data
