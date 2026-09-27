import uuid

from fastapi import APIRouter

from app.api.deps import CurrentChild, Db, Now
from app.schemas.lesson import (
    AnswerIn,
    AnswerResult,
    SessionIn,
    SessionOut,
    SessionSummary,
    Step,
)
from app.schemas.me import ChildOut, MeOut
from app.schemas.pair import PairIn, PairOut
from app.services import learning, overview, pairing

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/pair/{code}", response_model=PairOut)
async def pair_device(code: str, db: Db, now: Now, body: PairIn | None = None) -> PairOut:
    raw, child = await pairing.redeem_pair_code(db, code, now, body.device_name if body else None)
    return PairOut(device_token=raw, child=ChildOut(id=child.id, name=child.name))


@router.get("/me", response_model=MeOut)
async def me(db: Db, now: Now, child: CurrentChild) -> MeOut:
    return await overview.build_me(db, child, now)


@router.post("/sessions", response_model=SessionOut)
async def start_session(body: SessionIn, db: Db, now: Now, child: CurrentChild) -> SessionOut:
    session = await learning.build_session(db, child, body.topic_slug, now)
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
