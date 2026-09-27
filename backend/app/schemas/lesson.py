"""Wire shapes shared by the learning service, the API and the stored session plan."""

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models import ImageKind

StepType = Literal["intro", "listen", "recall"]


class ImageOut(BaseModel):
    kind: ImageKind
    value: str


class WordOut(BaseModel):
    slug: str
    topic_slug: str
    ka: str
    tr: str
    ru: str
    image: ImageOut
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
    week_lari: Decimal


class SessionSummary(BaseModel):
    session_id: uuid.UUID
    coins_gained: int
    learned: list[WordOut]
    week_coins: int
    week_lari: Decimal
