"""The app is served from TCMS's own origin: the shell at `/` and `/app/...`, its files at `/assets`, and every
other route (`/api/v1`, `/mcp`, `/healthz`, the docs) answers as before."""

import glob
import tempfile
import tomllib
from pathlib import Path

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms import app_shell
from test_junkie_tcms.app import create_app
from tests import support
from tests.test_mcp_server import make_admin_token, mcp_client, tool_names

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "test_junkie_tcms"
SHELL_PATHS = ("/", "/app", "/app/", "/app/cases/01J00000000000000000000000", "/app/runs/x/y")


def web_files() -> list[str]:
    return sorted(p.relative_to(app_shell.WEB_DIR).as_posix() for p in app_shell.WEB_DIR.rglob("*") if p.is_file())


def packaged(root: Path) -> set[str]:
    """The files under `root` that pyproject's package-data globs pick up, as setuptools expands them."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = pyproject["tool"]["setuptools"]["package-data"]["test_junkie_tcms"]
    found = set()
    for pattern in patterns:
        for match in glob.glob(str(root / pattern), recursive=True):
            if Path(match).is_file():
                found.add(Path(match).relative_to(root).as_posix())
    return found


@Suite(parameters=support.DATABASES)
class WebServing:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    # The shell

    @test()
    def test_the_shell_is_served_at_every_app_path(self, suite_parameter):
        client = self.env.client()
        shell = app_shell.SHELL.read_text(encoding="utf-8")
        for path in SHELL_PATHS:
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 200, (path, response.status_code)
            assert response.headers["content-type"].startswith("text/html"), path
            assert response.headers["cache-control"] == "no-cache", path
            assert response.text == shell, path
            head = client.head(path, follow_redirects=False)
            assert head.status_code == 200 and head.content == b"", path

    @test()
    def test_the_shell_refers_to_its_files_root_absolute(self, suite_parameter):
        shell = app_shell.SHELL.read_text(encoding="utf-8")
        assert 'href="/assets/app.css"' in shell and 'src="/assets/js/main.js"' in shell
        client = self.env.client()
        for ref in ("/assets/app.css", "/assets/js/main.js"):
            assert client.get(ref).status_code == 200, ref

    # The files

    @test()
    def test_every_web_file_is_served_at_assets(self, suite_parameter):
        client = self.env.client()
        files = web_files()
        assert {"index.html", "app.css", "js/main.js"} <= set(files), files
        for rel in files:
            response = client.get(f"/assets/{rel}")
            assert response.status_code == 200, rel
            assert response.content == (app_shell.WEB_DIR / rel).read_bytes(), rel

    @test()
    def test_a_nested_font_is_served_at_assets_fonts(self, suite_parameter):
        fonts = app_shell.WEB_DIR / "fonts"
        created = not fonts.exists()
        font = fonts / "test-only.woff2"
        fonts.mkdir(exist_ok=True)
        try:
            font.write_bytes(b"wOF2-test")
            response = self.env.client().get("/assets/fonts/test-only.woff2")
            assert response.status_code == 200 and response.content == b"wOF2-test"
        finally:
            font.unlink(missing_ok=True)
            if created:
                fonts.rmdir()

    @test()
    def test_a_missing_or_escaping_asset_is_a_problem_404(self, suite_parameter):
        client = self.env.client()
        for path in ("/assets/nope.js", "/assets/%2e%2e/app.py", "/assets/..%2fapp.py", "/assets/js/../../app.py"):
            response = client.get(path)
            assert response.status_code == 404, (path, response.status_code)
            assert response.headers["content-type"].startswith("application/problem+json"), path

    @test()
    def test_package_data_ships_every_web_file_and_nested_fonts(self, suite_parameter):
        shipped = packaged(PACKAGE)
        missing = [rel for rel in web_files() if f"web/{rel}" not in shipped]
        assert not missing, f"pyproject package-data drops {missing}"
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "web" / "fonts" / "inter.woff2"
            nested.parent.mkdir(parents=True)
            nested.write_bytes(b"")
            (Path(tmp) / "web" / "index.html").write_text("")
            assert packaged(Path(tmp)) >= {"web/fonts/inter.woff2", "web/index.html"}

    # Everything else answers as before

    @test()
    def test_api_unknown_paths_stay_problem_404s(self, suite_parameter):
        client = self.env.client()
        for path in ("/api/v1/nope", "/api/v1/orgs/acme/nope", "/api", "/mcpx", "/other", "/apps", "/app.css"):
            response = client.get(path)
            assert response.status_code == 404, (path, response.status_code)
            assert response.headers["content-type"].startswith("application/problem+json"), path

    @test()
    def test_healthz_docs_and_openapi_are_unchanged(self, suite_parameter):
        client = self.env.client()
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/api/v1/docs").headers["content-type"].startswith("text/html")
        spec = client.get("/api/v1/openapi.json").json()
        assert not [p for p in spec["paths"] if not p.startswith("/api/v1/")], "the shell leaks into OpenAPI"

    @test()
    def test_api_and_mcp_behave_as_without_the_shell(self, suite_parameter):
        owner = self.env.owner
        assert owner.get("/api/v1/orgs/acme").status_code == 200
        assert self.env.client().get("/api/v1/orgs/acme").status_code == 401
        admin_token = make_admin_token(owner)
        with mcp_client(self.env.app) as mcp:
            with_shell = tool_names(mcp, admin_token, "?toolsets=all")
        self.env.patch(app_shell, "install", lambda app: None)
        bare = create_app(self.env.settings, load_entry_points=False)
        try:
            with mcp_client(bare) as mcp:
                assert tool_names(mcp, admin_token, "?toolsets=all") == with_shell
                assert mcp.get("/").status_code == 404
        finally:
            bare.state.engine.dispose()
