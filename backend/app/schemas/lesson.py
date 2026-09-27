"""Wire shapes shared by the learning service, the API and the stored session plan."""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer

from app.models import ImageKind

StepType = Literal["intro", "listen", "recall"]

# GEL amounts are exact decimals internally and plain numbers on the wire.
Lari = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class ImageOut(BaseModel):
    kind: ImageKind
    value: str


class AnchorOut(BaseModel):
    """Example word for a letter card: "ბ as in ბურთი"."""

    ka: str
    tr: str
    ru: str
    emoji: str | None = None


class WordOut(BaseModel):
    slug: str
    topic_slug: str
    ka: str
    tr: str
    ru: str
    image: ImageOut
    anchor: AnchorOut | None = None
    audio_url: str


class Step(BaseModel):
    type: StepType
    word: WordOut
    # Empty for `intro`; 4 words for `listen`, 3 for `recall` (correct one included).
    options: list[WordOut] = Field(default_factory=list)


class AnswerIn(BaseModel):
    step_index: int = Field(ge=0)
    word_slug: str
    attempt: int = Field(ge=1)
    client_answer_id: uuid.UUID


class AnswerResult(BaseModel):
    correct: bool
    coins_gained: int
    word_learned: bool
    week_coins: int
    week_lari: Lari


class SessionIn(BaseModel):
    # The lesson number to play; None asks for a review-only session (every lesson done).
    lesson: int | None = None


class SessionOut(BaseModel):
    # None with empty steps means "nothing to do today".
    session_id: uuid.UUID | None
    steps: list[Step]


class SessionSummary(BaseModel):
    session_id: uuid.UUID
    coins_gained: int
    learned: list[WordOut]
    week_coins: int
    week_lari: Lari
