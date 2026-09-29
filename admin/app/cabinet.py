"""The parents' cabinet: read-only pages a parent opens from the bot as a Telegram Mini App.

Every route lives under /cabinet so that Caddy can proxy that prefix to this
process as is. Entry: the page asks Telegram (in the browser) for the signed
`initData` and posts it; the server verifies the signature, remembers the
Telegram id in a signed cookie for a month, and from then on renders pages by
reading /api/parent/* for that parent. A browser outside Telegram has no
`initData`, so it only ever sees "open it from the bot".
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.api import ApiError, ParentApi
from app.config import ADMIN_DIR, get_settings
from app.format import _plural, today_tbilisi
from app.telegram import telegram_user_id

COOKIE = "mziko_cabinet"
COOKIE_MAX_AGE = timedelta(days=30)
# `initData` is issued when the Mini App opens; older data was copied from somewhere.
INIT_DATA_MAX_AGE = timedelta(hours=1)
# A started topic that has not grown for this many days gets the "без продвижения" mark.
IDLE_DAYS = 7
LEARNED_STAGE = 3

SECTIONS = (("letters", "Буквы"), ("syllables", "Слоги"), ("words", "Слова"))
TABS = ("Прогресс", "Неделя", "Календарь", "Выплаты", "Код и устройства")

router = APIRouter(prefix="/cabinet")
templates = Jinja2Templates(directory=ADMIN_DIR / "app" / "templates")


def cards_count(n: int) -> str:
    return f"{n} {_plural(n, 'карточки', 'карточек', 'карточек')}"


templates.env.filters.update(cards_count=cards_count)


# --- view model ------------------------------------------------------------------


@dataclass
class WordView:
    ka: str
    ru: str
    stage: int


@dataclass
class TopicView:
    slug: str
    icon: str
    title: str
    learned: int
    total: int
    pct: int
    status: str  # "done" | "now" | ""
    idle_days: int | None
    words: list[WordView]


@dataclass
class SectionView:
    key: str
    title: str
    learned: int
    total: int
    topics: list[TopicView]


def topic_view(topic: dict[str, Any], today: date) -> TopicView:
    words = [WordView(w["ka"], w["ru"], w["stage"]) for w in topic["words"]]
    learned, total = topic["learned"], topic["total"]
    started = any(w.stage > 0 for w in words)
    done = total > 0 and learned >= total
    idle_days = None
    if started and not done:
        last_days = [
            date.fromisoformat(w["last_correct_date"])
            for w in topic["words"]
            if w.get("last_correct_date")
        ]
        if last_days:
            idle = (today - max(last_days)).days
            idle_days = idle if idle >= IDLE_DAYS else None
    return TopicView(
        slug=topic["slug"],
        icon=topic["icon"],
        title=topic["title_ru"],
        learned=learned,
        total=total,
        pct=round(100 * learned / total) if total else 0,
        status="done" if done else ("now" if started else ""),
        idle_days=idle_days,
        words=words,
    )


def build_sections(topics: list[dict[str, Any]], today: date) -> list[SectionView]:
    """Topics grouped into the programme's three sections, in the app's order."""
    views = [(t["section"], topic_view(t, today)) for t in topics]
    sections = []
    for key, title in SECTIONS:
        mine = [v for section, v in views if section == key]
        sections.append(
            SectionView(
                key=key,
                title=title,
                learned=sum(v.learned for v in mine),
                total=sum(v.total for v in mine),
                topics=mine,
            )
        )
    return sections


# --- session cookie ----------------------------------------------------------------


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().admin_session_secret, salt="mziko-cabinet")


def current_telegram_id(request: Request) -> int | None:
    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    try:
        value = _serializer().loads(raw, max_age=int(COOKIE_MAX_AGE.total_seconds()))
    except BadSignature:
        return None
    return value if isinstance(value, int) else None


def set_session(response: Response, telegram_id: int) -> None:
    response.set_cookie(
        COOKIE,
        _serializer().dumps(telegram_id),
        max_age=int(COOKIE_MAX_AGE.total_seconds()),
        path="/cabinet",
        httponly=True,
        samesite="lax",
        secure=get_settings().public_url.startswith("https://"),
    )


def get_parent_api(request: Request) -> ParentApi:
    api: ParentApi = request.app.state.parent_api
    return api


TelegramId = Annotated[int | None, Depends(current_telegram_id)]
Api = Annotated[ParentApi, Depends(get_parent_api)]


def page(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def entry(request: Request, state: str, status_code: int = 200) -> HTMLResponse:
    """The page without a session: `gate` asks Telegram for initData, the rest explain."""
    return page(request, "cabinet_entry.html", status_code, state=state)


# --- routes ---------------------------------------------------------------------


@router.post("/session")
async def session(request: Request) -> Response:
    # A plain urlencoded form with one field; parsed by hand to keep multipart support out.
    form = dict(parse_qsl((await request.body()).decode(errors="replace")))
    init_data = form.get("init_data", "")
    telegram_id = telegram_user_id(
        init_data, get_settings().bot_token, datetime.now(UTC), INIT_DATA_MAX_AGE
    )
    if telegram_id is None:
        return entry(request, "denied", status.HTTP_401_UNAUTHORIZED)
    # `in=1` tells the entry page not to try again if the cookie did not stick.
    response = RedirectResponse("/cabinet/?in=1", status.HTTP_303_SEE_OTHER)
    set_session(response, telegram_id)
    return response


@router.get("/", response_class=HTMLResponse)
async def progress(request: Request, telegram_id: TelegramId, api: Api) -> HTMLResponse:
    if telegram_id is None:
        just_entered = request.query_params.get("in") == "1"
        return entry(request, "denied" if just_entered else "gate")
    try:
        children = await api.children(telegram_id)
    except ApiError as exc:
        if exc.status == 403:
            return entry(request, "unregistered")
        return page(request, "cabinet_progress.html", tabs=TABS, error=str(exc))
    if not children:
        return page(request, "cabinet_progress.html", tabs=TABS, children=[], child=None)

    wanted = request.query_params.get("child", "")
    child = next((c for c in children if str(c["id"]) == wanted), children[0])
    try:
        data = await api.progress(telegram_id, child["id"])
    except ApiError as exc:
        return page(request, "cabinet_progress.html", tabs=TABS, error=str(exc))
    sections = build_sections(data["topics"], today_tbilisi())
    return page(
        request,
        "cabinet_progress.html",
        tabs=TABS,
        children=children,
        child=child,
        sections=sections,
        learned=sum(s.learned for s in sections),
        total=sum(s.total for s in sections),
        started=any(t.status for s in sections for t in s.topics),
    )
