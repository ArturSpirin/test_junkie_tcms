"""Serves the app: the packaged `web/` files at `/assets`, and `index.html` for the app's own paths.

The shell is served at deep paths like `/app/cases/X`, so it refers to its files root-absolute
(`/assets/app.css`, `/assets/js/main.js`). Only `/`, `/app` and `/app/...` fall back to the shell: every other
unknown path keeps its problem+json 404, so `/api/v1/...` never answers with HTML.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path(__file__).parent / "web"
SHELL = WEB_DIR / "index.html"
SHELL_PATHS = ("/", "/app", "/app/{path:path}")


def _shell() -> FileResponse:
    return FileResponse(SHELL, media_type="text/html", headers={"Cache-Control": "no-cache"})


def install(app: FastAPI) -> None:
    """Call last in `create_app`, after the plugins, so no app route is shadowed.

    `/app/` with a trailing slash serves the shell too (it matches `/app/{path}` with an empty path).
    """
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")
    for path in SHELL_PATHS:
        # Not op()-marked and outside /api/v1, so the MCP generator makes no tool from it.
        app.add_api_route(path, _shell, methods=["GET", "HEAD"], include_in_schema=False)
