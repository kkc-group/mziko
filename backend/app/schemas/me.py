"""Response of GET /api/me: everything the home screen needs in one call."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.lesson import Lari, WordOut


class ChildOut(BaseModel):
    id: int
    name: str


class SettingsOut(BaseModel):
    rate: int
    cap_lari: int
    show_hint: bool


class WeekOut(BaseModel):
    week_start: date
    today: date
    coins: int
    lari: Lari
    study_days: list[date]


class LessonOut(BaseModel):
    """One step of the child's path: a topic, or a part of a bigger one."""

    number: int
    topic_slug: str
    title_ru: str
    icon: str
    part: int
    parts: int
    total: int
    introduced: int
    status: Literal["done", "current", "locked"]
    playable: bool  # "Играть" / "Повторить" is available today


class StickerOut(BaseModel):
    word: WordOut
    learned: bool


class MeOut(BaseModel):
    child: ChildOut
    settings: SettingsOut
    week: WeekOut
    lessons: list[LessonOut]
    review_available: bool  # older words wait for a review (the "all done" button)
    stickers: list[StickerOut]
