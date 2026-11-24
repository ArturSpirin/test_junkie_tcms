"""Serves the app: the packaged `web/` files at `/assets`, and `index.html` for the app's own paths.

The shell is served at deep paths like `/app/cases/X`, so it refers to its files root-absolute
(`/assets/app.css`, `/assets/js/main.js`). Only `/`, `/app` and `/app/...` fall back to the shell: every other
unknown path keeps its problem+json 404, so `/api/v1/...` never answers with HTML.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path(__file__).parent / "web"
SHELL = WEB_DIR / "index.html"
SHELL_PATHS = ("/", "/app", "/app/{path:path}")
FAVICON = "/assets/favicon.svg"


def _shell() -> FileResponse:
    return FileResponse(SHELL, media_type="text/html", headers={"Cache-Control": "no-cache"})


def _favicon() -> RedirectResponse:
    # The shell links the SVG; browsers and crawlers that ask `/favicon.ico` directly get the same one file.
    return RedirectResponse(FAVICON, status_code=307)


class _Assets(StaticFiles):
    """`/assets` files are revalidated on every load (ETag/Last-Modified, a 304 when unchanged), so an
    upgrade never leaves a browser running stale JS. `file_response` returns both the 200 and the 304."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def install(app: FastAPI) -> None:
    """Call last in `create_app`, after the plugins, so no app route is shadowed.

    `/app/` with a trailing slash serves the shell too (it matches `/app/{path}` with an empty path).
    """
    app.mount("/assets", _Assets(directory=WEB_DIR), name="assets")
    for path in SHELL_PATHS:
        # Not op()-marked and outside /api/v1, so the MCP generator makes no tool from it.
        app.add_api_route(path, _shell, methods=["GET", "HEAD"], include_in_schema=False)
    app.add_api_route("/favicon.ico", _favicon, methods=["GET", "HEAD"], include_in_schema=False)
