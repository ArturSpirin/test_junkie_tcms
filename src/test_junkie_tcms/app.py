from fastapi import FastAPI

from test_junkie_tcms import __version__, errors
from test_junkie_tcms.api.v1 import router as v1_router
from test_junkie_tcms.db.session import make_engine, make_sessionmaker
from test_junkie_tcms.plugins import RetentionPolicy, load_plugins
from test_junkie_tcms.settings import Settings


def create_app(settings: Settings | None = None, load_entry_points: bool = True) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="Test Junkie TCMS",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.audit_retention = RetentionPolicy()
    errors.install(app)
    app.include_router(v1_router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok"}

    app.state.plugins = load_plugins(app) if load_entry_points else []
    return app
