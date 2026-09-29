"""Mziko back office: Google sign-in for one owner, pages rendered from the API.

Every route lives under /admin so that Caddy can proxy that prefix as is.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.api import AdminApi, ApiError, ParentApi, make_client, make_parent_client
from app.cabinet import router as cabinet_router
from app.calendar import calendar_grid
from app.config import ADMIN_DIR, get_settings
from app.format import (
    activity_class,
    children_count,
    is_current_week,
    lari,
    last_week_label,
    parents_count,
    registered_date,
    relative_date,
    short_date,
    this_week_label,
    today_tbilisi,
    words_count,
)

SESSION_COOKIE = "mziko_admin"
GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"

templates = Jinja2Templates(directory=ADMIN_DIR / "app" / "templates")
templates.env.filters.update(
    relative_date=relative_date,
    activity_class=activity_class,
    registered_date=registered_date,
    lari=lari,
    words_count=words_count,
    parents_count=parents_count,
    children_count=children_count,
    this_week_label=this_week_label,
    last_week_label=last_week_label,
    short_date=short_date,
    is_current_week=is_current_week,
    calendar_grid=calendar_grid,
)
router = APIRouter(prefix="/admin")


@dataclass
class Identity:
    """What Google told us about the person who just signed in."""

    email: str
    verified: bool


@dataclass
class GoogleOutcome:
    identity: Identity | None = None
    # Google returned an error or the account picker was closed.
    failed: bool = False


def make_oauth() -> OAuth:
    s = get_settings()
    oauth = OAuth()
    oauth.register(
        "google",
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        server_metadata_url=GOOGLE_METADATA,
        client_kwargs={"scope": "openid email"},
    )
    return oauth


# --- dependencies ---------------------------------------------------------------


def get_api(request: Request) -> AdminApi:
    api: AdminApi = request.app.state.api
    return api


async def google_redirect(request: Request) -> Response:
    oauth: OAuth = request.app.state.oauth
    response: Response = await oauth.google.authorize_redirect(
        request, get_settings().redirect_uri, prompt="select_account"
    )
    return response


async def google_outcome(request: Request) -> GoogleOutcome:
    """Finish the OAuth dance. Tests override this to skip Google."""
    if request.query_params.get("error"):
        return GoogleOutcome(failed=True)
    oauth: OAuth = request.app.state.oauth
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return GoogleOutcome(failed=True)
    info: dict[str, Any] = token.get("userinfo") or {}
    email = info.get("email")
    if not email:
        return GoogleOutcome(failed=True)
    return GoogleOutcome(Identity(email=email, verified=bool(info.get("email_verified"))))


def current_email(request: Request) -> str:
    """The signed-in owner; anyone else is sent to the login page."""
    email = request.session.get("email")
    if not isinstance(email, str) or not email:
        expired = SESSION_COOKIE in request.cookies
        target = "/admin/login" + ("?expired=1" if expired else "")
        raise HTTPException(status.HTTP_303_SEE_OTHER, headers={"Location": target})
    return email


Api = Annotated[AdminApi, Depends(get_api)]
Owner = Annotated[str, Depends(current_email)]
GoogleRedirect = Annotated[Response, Depends(google_redirect)]
Outcome = Annotated[GoogleOutcome, Depends(google_outcome)]


def is_owner(identity: Identity) -> bool:
    expected = get_settings().admin_email.strip().lower()
    return bool(expected) and identity.verified and identity.email.strip().lower() == expected


def page(request: Request, name: str, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {"email": None, **context})


# --- routes ---------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login(request: Request) -> Response:
    if request.session.get("email"):
        return RedirectResponse("/admin/", status.HTTP_303_SEE_OTHER)
    return page(
        request,
        "login.html",
        state="start",
        expired=request.query_params.get("expired") == "1",
    )


@router.get("/login/google")
async def login_google(response: GoogleRedirect) -> Response:
    return response


@router.get("/login/callback", response_class=HTMLResponse)
async def login_callback(request: Request, outcome: Outcome) -> Response:
    if outcome.failed or outcome.identity is None:
        return page(request, "login.html", state="failed")
    if not is_owner(outcome.identity):
        request.session.clear()
        return page(request, "login.html", state="denied", email=outcome.identity.email)
    request.session.clear()
    request.session["email"] = outcome.identity.email
    return RedirectResponse("/admin/", status.HTTP_303_SEE_OTHER)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/admin/login", status.HTTP_303_SEE_OTHER)


@router.get("/", response_class=HTMLResponse)
async def parents(request: Request, email: Owner, api: Api) -> HTMLResponse:
    today = today_tbilisi()
    try:
        rows = await api.parents()
    except ApiError as exc:
        return page(request, "parents.html", email=email, rows=None, error=str(exc), today=today)
    return page(request, "parents.html", email=email, rows=rows, error=None, today=today)


@router.get("/parents/{parent_id}", response_class=HTMLResponse)
async def parent(request: Request, parent_id: int, email: Owner, api: Api) -> HTMLResponse:
    today = today_tbilisi()
    try:
        card = await api.parent(parent_id)
    except ApiError as exc:
        not_found = exc.status == 404
        return page(
            request,
            "parent.html",
            email=email,
            parent=None,
            parent_id=parent_id,
            not_found=not_found,
            error=None if not_found else str(exc),
            today=today,
        )
    return page(
        request,
        "parent.html",
        email=email,
        parent=card,
        parent_id=parent_id,
        not_found=False,
        error=None,
        today=today,
    )


# --- app ------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    s = get_settings()
    app.state.oauth = make_oauth()
    app.state.api = AdminApi(make_client(s.api_url, s.admin_api_token))
    app.state.parent_api = ParentApi(make_parent_client(s.api_url, s.bot_api_token))
    yield


def create_app() -> FastAPI:
    s = get_settings()
    if not s.admin_session_secret:
        raise RuntimeError("ADMIN_SESSION_SECRET is required (openssl rand -hex 32)")
    app = FastAPI(title="Mziko back office", docs_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=s.admin_session_secret,
        session_cookie=SESSION_COOKIE,
        path="/admin",
        same_site="lax",
        https_only=s.public_url.startswith("https://"),
        max_age=14 * 24 * 3600,
    )
    app.include_router(router)
    app.include_router(cabinet_router)
    static = StaticFiles(directory=ADMIN_DIR / "app" / "static")
    app.mount("/admin/static", static, name="static")
    app.mount("/cabinet/static", static, name="cabinet_static")

    @app.exception_handler(HTTPException)
    async def redirect_or_error(request: Request, exc: HTTPException) -> Response:
        location = (exc.headers or {}).get("Location")
        if location:
            return RedirectResponse(location, exc.status_code)
        return HTMLResponse(str(exc.detail), exc.status_code)

    return app


app = create_app()
