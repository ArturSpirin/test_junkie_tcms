"""A real TCMS server for the web adapter tests, and the node harness that runs the shipped adapters on it.

``LiveServer(kind)`` serves ``support.Env(kind).app`` (orgs acme and globex, a fresh database) on uvicorn at a
free port, in a thread; ``close()`` stops the server, joins the thread and closes the Env.
``run_js(server, code)`` runs ``code`` (the body of an async JS function of ``h``) in node through
``adapter_harness.mjs``, which loads the shipped ``web/js/api.js`` and adapters with a cookie-jar ``fetch``
against the server; it returns what the code returns, as JSON.
"""

import json
import shutil
import subprocess
import threading
import time
from http import HTTPStatus
from pathlib import Path

import uvicorn

from tests import support

HARNESS = Path(__file__).parent / "adapter_harness.mjs"


class LiveServer:
    def __init__(self, kind: str):
        self.env = support.Env(kind)
        app = self.env.app
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, name="tcms-live-server", daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 20
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                self.close()
                raise AssertionError("the live TCMS server did not start")
            time.sleep(0.02)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"

    @property
    def owner(self):
        """A TestClient signed in as the acme owner, on the same app and database: for seeding."""
        return self.env.owner

    def close(self) -> None:
        self.server.should_exit = True
        if self.thread.is_alive():
            self.thread.join(timeout=20)
        assert not self.thread.is_alive(), "the live TCMS server did not stop"
        self.env.close()


def as_sent(resp) -> str:
    """A refused call as the app shows it raw (``api.js`` ``ApiError.raw``): the status line, Content-Type,
    a blank line, then the body. ``resp`` is a TestClient response, which skips uvicorn, so the reason
    phrase is the one uvicorn sends (``http.HTTPStatus``)."""
    status = f"HTTP/1.1 {resp.status_code} {HTTPStatus(resp.status_code).phrase}"
    return f"{status}\nContent-Type: {resp.headers['content-type']}\n\n{resp.text}"


def body_of(raw: str) -> dict:
    """The JSON body of a raw refusal (what ``as_sent`` builds and the app shows)."""
    return json.loads(raw.split("\n\n", 1)[1])


def run_js(server: LiveServer, code: str, url: str = "/app?view=products") -> object:
    """Run ``code`` as ``async (h) => { <code> }``, the page at ``url``; adapter_harness.mjs has ``h``."""
    node = shutil.which("node")
    if node is None:
        raise AssertionError(
            "node is not on PATH: the web adapter tests need node (no packages) to run "
            "tests/web/adapter_harness.mjs. Install node; these tests never skip."
        )
    proc = subprocess.run(
        [node, str(HARNESS), server.url, url],
        input=code,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert proc.returncode == 0, f"adapter_harness.mjs exited {proc.returncode}:\n{proc.stderr}"
    return json.loads(proc.stdout)
