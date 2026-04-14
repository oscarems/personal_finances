"""
Authentication module — single-user session via signed cookies.

Uses itsdangerous to sign a session cookie. The password is read from
the APP_PASSWORD environment variable; SECRET_KEY signs the cookie.
"""

import os

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from pathlib import Path

from finance_app.config import SECRET_KEY

COOKIE_NAME = "session"
MAX_AGE = 30 * 24 * 3600  # 30 days
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
USE_SECURE_COOKIE = os.getenv("HTTPS", "").lower() in {"true", "1", "yes"}

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()

_signer = TimestampSigner(SECRET_KEY)


def _valid_session(request: Request) -> bool:
    """Authentication disabled — always returns True."""
    return True


# ---------------------------------------------------------------------------
# Auth dependency + exception handler
# ---------------------------------------------------------------------------

class _AuthRedirect(Exception):
    """Raised to trigger a redirect to the login page."""


async def require_auth(request: Request):
    """FastAPI dependency — raises _AuthRedirect when unauthenticated."""
    if not _valid_session(request):
        raise _AuthRedirect()


def register_auth_exception_handler(app):
    """Register the exception handler that redirects to /login."""
    @app.exception_handler(_AuthRedirect)
    async def _handler(request: Request, exc: _AuthRedirect):
        return RedirectResponse(url="/login", status_code=303)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _valid_session(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/auth/login")
async def login(request: Request, password: str = Form(...)):
    if password == APP_PASSWORD:
        response = RedirectResponse(url="/", status_code=303)
        signed = _signer.sign("authenticated").decode()
        response.set_cookie(
            key=COOKIE_NAME,
            value=signed,
            max_age=MAX_AGE,
            httponly=True,
            secure=USE_SECURE_COOKIE,
            samesite="lax",
        )
        return response
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Contraseña incorrecta",
    })


@router.get("/auth/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=COOKIE_NAME)
    return response
