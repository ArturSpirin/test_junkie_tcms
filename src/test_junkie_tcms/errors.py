"""Errors as RFC 9457 `application/problem+json`."""

from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM = "application/problem+json"


def problem(status: int, detail: str | None = None, headers=None, **extra) -> JSONResponse:
    body = {"type": "about:blank", "title": HTTPStatus(status).phrase, "status": status}
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM, headers=headers)


class ProblemError(HTTPException):
    """An HTTPException whose problem body carries extra members, e.g. `current_version`."""

    def __init__(self, status: int, detail: str, headers=None, **extra):
        super().__init__(status, detail, headers)
        self.extra = extra


async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else None
    extra = getattr(exc, "extra", {})
    return problem(exc.status_code, detail, headers=getattr(exc, "headers", None), **extra)


def _is_missing_if_match(error: dict) -> bool:
    loc = [str(part).lower() for part in error.get("loc", ())]
    return loc == ["header", "if-match"] and error.get("type") == "missing"


async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    if any(_is_missing_if_match(e) for e in exc.errors()):
        return problem(428, "If-Match header is required: send the case's current version")
    errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
    return problem(422, "Request is not valid", errors=errors)


async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
    return problem(409, "Conflicts with existing data")


def install(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(IntegrityError, _integrity)
