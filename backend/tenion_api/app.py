from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .database import RegistrationDatabase
from .service import ContactService, RegistrationIssue, RegistrationService


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    username: str = Field(min_length=3, max_length=64)
    consent: bool
    website: str = Field(default="", max_length=200)


class ContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=10, max_length=4000)
    topic: str = Field(min_length=4, max_length=10)
    website: str = Field(default="", max_length=200)


settings = Settings.from_environment()
database = RegistrationDatabase(settings.data_root / "tenion.db")
service = RegistrationService(settings, database)
contact_service = ContactService(settings, database)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.initialize()
    yield


app = FastAPI(
    title="Tenion portal API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.exception_handler(RegistrationIssue)
async def registration_issue_handler(_: Request, error: RegistrationIssue):
    return JSONResponse(
        status_code=error.status,
        content={"ok": False, "error": {"code": error.code, "message": str(error)}},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def client_ip(request: Request) -> str:
    value = request.client.host if request.client else "unknown"
    if value in {"127.0.0.1", "::1"}:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            value = forwarded_for.split(",", 1)[0].strip()
    return value


@app.post("/api/register", status_code=201)
def register(
    payload: RegistrationRequest,
    request: Request,
    origin: Annotated[str | None, Header()] = None,
):
    if origin != settings.public_origin:
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": {"code": "INVALID_ORIGIN", "message": "Запрос отклонён."},
            },
            headers={"Cache-Control": "no-store"},
        )
    if payload.website:
        return JSONResponse(
            status_code=201,
            content={"ok": True},
            headers={"Cache-Control": "no-store"},
        )
    if payload.consent is not True:
        raise RegistrationIssue(
            "CONSENT_REQUIRED",
            "Подтвердите согласие на обработку email для создания доступа.",
            status=422,
        )

    service.register(payload.email, payload.username, client_ip(request))
    return JSONResponse(
        status_code=201,
        content={
            "ok": True,
            "message": "Доступ создан. Логин и пароль отправлены на вашу почту.",
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/contact", status_code=201)
def contact(
    payload: ContactRequest,
    request: Request,
    origin: Annotated[str | None, Header()] = None,
):
    if origin != settings.public_origin:
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": {"code": "INVALID_ORIGIN", "message": "Запрос отклонён."},
            },
            headers={"Cache-Control": "no-store"},
        )
    if payload.website:
        return JSONResponse(
            status_code=201,
            content={"ok": True},
            headers={"Cache-Control": "no-store"},
        )

    contact_service.send(
        payload.name,
        payload.email,
        payload.message,
        payload.topic,
        client_ip(request),
    )
    return JSONResponse(
        status_code=201,
        content={
            "ok": True,
            "message": "Сообщение отправлено. Мы ответим на указанную почту.",
        },
        headers={"Cache-Control": "no-store"},
    )
