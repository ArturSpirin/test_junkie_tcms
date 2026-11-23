import contextlib

from fastapi import FastAPI

from test_junkie_tcms import __version__, app_shell, errors
from test_junkie_tcms.api import idempotency, request_context
from test_junkie_tcms.api.v1 import router as v1_router
from test_junkie_tcms.db.session import make_engine, make_sessionmaker
from test_junkie_tcms.mcp_server import server as mcp_server
from test_junkie_tcms.plugins import RetentionPolicy, load_plugins
from test_junkie_tcms.settings import Settings


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # The MCP tools are built here, not in create_app, so they include every plugin router.
    async with mcp_server.lifespan(app):
        yield


def create_app(settings: Settings | None = None, load_entry_points: bool = True) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="Test Junkie TCMS",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.audit_retention = RetentionPolicy()
    errors.install(app)
    idempotency.install(app)
    request_context.install(app)
    app.include_router(v1_router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok"}

    mcp_server.install(app)
    app.state.plugins = load_plugins(app) if load_entry_points else []
    app_shell.install(app)
    return app
