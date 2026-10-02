"""The parents' cabinet: pages a parent opens from the bot as a Telegram Mini App.

Every route lives under /cabinet so that Caddy can proxy that prefix to this
process as is. Entry: the page asks Telegram (in the browser) for the signed
`initData` and posts it; the server verifies the signature, remembers the
Telegram id in a signed cookie for a month, and from then on renders pages by
reading /api/parent/* for that parent. A browser outside Telegram has no
`initData`, so it only ever sees "open it from the bot".

The one thing a parent changes here is a topic's access. The form is a plain
POST; the session cookie is SameSite=Lax, so another site cannot post it for
the parent, and the API checks that the child is the parent's own.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import parse_qsl, quote

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.api import ApiError, ParentApi
from app.config import ADMIN_DIR, get_settings
from app.format import _plural, today_tbilisi, words_count
from app.telegram import telegram_photo_url, telegram_user_id

COOKIE = "mziko_cabinet"
COOKIE_MAX_AGE = timedelta(days=30)
# `initData` is issued when the Mini App opens; older data was copied from somewhere.
INIT_DATA_MAX_AGE = timedelta(hours=1)
# A started topic that has not grown for this many days gets the "без продвижения" mark.
IDLE_DAYS = 7
LEARNED_STAGE = 3

SECTIONS = (("letters", "Буквы"), ("syllables", "Слоги"), ("words", "Слова"))
TABS = ("Прогресс", "Неделя", "Календарь", "Выплаты", "Код и устройства")
# A topic's access: the value the API takes and the label on the switch.
ACCESS = (("auto", "По порядку"), ("open", "Открыта"), ("closed", "Закрыта"))

router = APIRouter(prefix="/cabinet")
templates = Jinja2Templates(directory=ADMIN_DIR / "app" / "templates")


def cards_count(n: int) -> str:
    return f"{n} {_plural(n, 'карточки', 'карточек', 'карточек')}"


templates.env.filters.update(cards_count=cards_count, words_count=words_count)


# --- view model ------------------------------------------------------------------


@dataclass
class WordView:
    ka: str
    ru: str
    stage: int
    introduced: bool  # met on a lesson; False words are faded, stage-0 met words say "показано"


@dataclass
class TopicView:
    slug: str
    icon: str
    title: str
    learned: int
    in_work: int  # met on a lesson, not learned yet
    total: int
    pct: int  # learned, of total
    pct_started: int  # learned + in work, of total: the light part of the bar
    status: str  # "done" | "now" | ""
    idle_days: int | None
    words: list[WordView]
    access: str = "auto"  # the parent's say: "auto" | "open" | "closed"
    access_note: str = ""  # what that comes to for the child today

    @property
    def unseen(self) -> int:
        return sum(1 for w in self.words if not w.introduced)


@dataclass
class SectionView:
    key: str
    title: str
    learned: int
    in_work: int
    total: int
    topics: list[TopicView]


def _pct(part: int, total: int) -> int:
    return round(100 * part / total) if total else 0


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def access_note(topic: dict[str, Any]) -> str:
    """One line under the switch: what the topic's access means for the child right now."""
    access = topic.get("access", "auto")
    if access == "open":
        return "Ребёнок может начать тему сразу, не дожидаясь очереди и завтрашнего дня."
    if access == "closed":
        return (
            "У ребёнка на теме замок, «Повторить» тоже недоступно. "
            "Выученные слова и наклейки остаются."
        )
    if topic.get("status", "open") != "locked":
        return "Тема идёт по порядку. Сейчас открыта."
    if topic.get("waits_for"):
        return f"Тема идёт по порядку. Откроется после темы «{topic['waits_for']}»."
    return "Тема идёт по порядку. Откроется завтра: сегодня в этом разделе уже начата новая тема."


def topic_view(topic: dict[str, Any], today: date) -> TopicView:
    words = [
        WordView(w["ka"], w["ru"], w["stage"], w.get("introduced", False)) for w in topic["words"]
    ]
    learned, total = topic["learned"], topic["total"]
    in_work = sum(1 for w in words if w.introduced and w.stage < LEARNED_STAGE)
    started = any(w.introduced for w in words)
    done = total > 0 and learned >= total
    access = topic.get("access", "auto")
    idle_days = None
    # A topic the parent closed could not have grown: no idle mark on it.
    if started and not done and access != "closed":
        # The last day anything happened to the topic: a stage grew, or failing
        # that a word was first shown (all-wrong first days have no correct date).
        activity = [
            _day(w.get("last_correct_date")) or _day(w.get("introduced_on")) for w in topic["words"]
        ]
        last_days = [d for d in activity if d is not None]
        if last_days:
            idle = (today - max(last_days)).days
            idle_days = idle if idle >= IDLE_DAYS else None
    return TopicView(
        slug=topic["slug"],
        icon=topic["icon"],
        title=topic["title_ru"],
        learned=learned,
        in_work=in_work,
        total=total,
        pct=_pct(learned, total),
        pct_started=_pct(learned + in_work, total),
        status="done" if done else ("now" if started else ""),
        idle_days=idle_days,
        words=words,
        access=access,
        access_note=access_note(topic),
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
                in_work=sum(v.in_work for v in mine),
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


async def posted_init_data(request: Request) -> tuple[str, int | None]:
    """The `init_data` field of the posted form and the Telegram id it proves, if any."""
    # A plain urlencoded form with one field; parsed by hand to keep multipart support out.
    form = dict(parse_qsl((await request.body()).decode(errors="replace")))
    init_data = form.get("init_data", "")
    telegram_id = telegram_user_id(
        init_data, get_settings().bot_token, datetime.now(UTC), INIT_DATA_MAX_AGE
    )
    return init_data, telegram_id


@router.post("/session")
async def session(request: Request) -> Response:
    _, telegram_id = await posted_init_data(request)
    if telegram_id is None:
        return entry(request, "denied", status.HTTP_401_UNAUTHORIZED)
    # `in=1` tells the entry page not to try again if the cookie did not stick.
    response = RedirectResponse("/cabinet/?in=1", status.HTTP_303_SEE_OTHER)
    set_session(response, telegram_id)
    return response


@router.post("/photo", status_code=status.HTTP_204_NO_CONTENT)
async def photo(request: Request, api: Api) -> None:
    """Every cabinet page posts Telegram's `initData` here in the background.

    The session cookie lasts a month, so the entry alone would see the profile
    photo once a month. The photo is for the back office only: the answer is
    204 whatever happened, and nothing here can break a page. No photo in
    Telegram's data keeps the saved one: a link is replaced, never cleared.
    """
    init_data, telegram_id = await posted_init_data(request)
    photo_url = telegram_photo_url(init_data)
    if telegram_id is None or photo_url is None:
        return
    try:
        await api.set_photo(telegram_id, photo_url)
    except ApiError:
        pass


@router.post("/topics/{slug}/access")
async def topic_access(
    slug: str, request: Request, telegram_id: TelegramId, api: Api
) -> RedirectResponse:
    """The switch inside a topic: save, then come back to the same topic, opened."""
    if telegram_id is None:
        return RedirectResponse("/cabinet/", status.HTTP_303_SEE_OTHER)
    form = dict(parse_qsl((await request.body()).decode(errors="replace")))
    child, access = form.get("child", ""), form.get("access", "")
    saved = child.isdigit() and access in dict(ACCESS)
    if saved:
        try:
            await api.set_topic_access(telegram_id, int(child), slug, access)
        except ApiError:
            saved = False
    back = f"/cabinet/?child={quote(child)}&open={quote(slug)}"
    if not saved:
        back += "&failed=1"
    return RedirectResponse(f"{back}#t-{quote(slug)}", status.HTTP_303_SEE_OTHER)


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
    learned = sum(s.learned for s in sections)
    in_work = sum(s.in_work for s in sections)
    total = sum(s.total for s in sections)
    return page(
        request,
        "cabinet_progress.html",
        tabs=TABS,
        children=children,
        child=child,
        sections=sections,
        learned=learned,
        in_work=in_work,
        total=total,
        pct=_pct(learned, total),
        pct_started=_pct(learned + in_work, total),
        lessons_done=data.get("lessons_done", 0),
        started=any(t.status for s in sections for t in s.topics),
        access_options=ACCESS,
        open_slug=request.query_params.get("open", ""),
        failed=request.query_params.get("failed") == "1",
    )
