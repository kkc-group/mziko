import uuid

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.deps import ClientIp, CurrentChild, Db, Now
from app.schemas.lesson import (
    AnswerIn,
    AnswerResult,
    SessionIn,
    SessionOut,
    SessionSummary,
    Step,
)
from app.schemas.login import LockedDetail, LockStatusOut, LoginIn, LoginOut, WrongCodeDetail
from app.schemas.me import ChildOut, MeOut
from app.services import learning, login_codes, overview
from app.services.errors import LoginLocked, WrongCode

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _login_error(status_code: int, detail: BaseModel) -> JSONResponse:
    return JSONResponse({"detail": detail.model_dump(mode="json")}, status_code=status_code)


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, db: Db, now: Now, ip: ClientIp) -> LoginOut | JSONResponse:
    """Child login by the permanent code. 401 with attempts_left, 423 with locked_until.

    Errors are returned, not raised: the Db dependency commits only on a normal
    return, and a miss must be recorded or the hour lock would never happen.
    """
    try:
        raw, child = await login_codes.login(db, ip, body.word, body.pin, now, body.device_name)
    except WrongCode as exc:
        return _login_error(
            status.HTTP_401_UNAUTHORIZED, WrongCodeDetail(attempts_left=exc.attempts_left)
        )
    except LoginLocked as exc:
        return _login_error(status.HTTP_423_LOCKED, LockedDetail(locked_until=exc.locked_until))
    return LoginOut(device_token=raw, child=ChildOut(id=child.id, name=child.name))


@router.get("/login/status", response_model=LockStatusOut)
async def login_status(db: Db, now: Now, ip: ClientIp) -> LockStatusOut:
    """Polled by the lock screen: is this address still locked, did the parent re-issue the pin."""
    s = await login_codes.lock_status(db, ip, now)
    return LockStatusOut(locked_until=s.locked_until, word=s.word, pin_rotated=s.pin_rotated)


@router.get("/me", response_model=MeOut)
async def me(db: Db, now: Now, child: CurrentChild) -> MeOut:
    return await overview.build_me(db, child, now)


@router.post("/sessions", response_model=SessionOut)
async def start_session(body: SessionIn, db: Db, now: Now, child: CurrentChild) -> SessionOut:
    session = await learning.build_session(db, child, body.lesson, now)
    if session is None:
        return SessionOut(session_id=None, steps=[])
    return SessionOut(session_id=session.id, steps=[Step.model_validate(s) for s in session.steps])


@router.post("/topics/{slug}/restart", response_model=SessionOut)
async def restart_topic(slug: str, db: Db, now: Now, child: CurrentChild) -> SessionOut:
    """Start the topic over from its first lesson; 404 unknown topic, 409 locked today."""
    session = await learning.restart_topic(db, child, slug, now)
    if session is None:
        return SessionOut(session_id=None, steps=[])
    return SessionOut(session_id=session.id, steps=[Step.model_validate(s) for s in session.steps])


@router.post("/sessions/{session_id}/answers", response_model=AnswerResult)
async def answer(
    session_id: uuid.UUID, body: AnswerIn, db: Db, now: Now, child: CurrentChild
) -> AnswerResult:
    return await learning.submit_answer(db, child, session_id, body, now)


@router.post("/sessions/{session_id}/finish", response_model=SessionSummary)
async def finish(session_id: uuid.UUID, db: Db, now: Now, child: CurrentChild) -> SessionSummary:
    return await learning.finish_session(db, child, session_id, now)
