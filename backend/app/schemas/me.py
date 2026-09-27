"""Response of GET /api/me: everything the home screen needs in one call."""

from datetime import date

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


class TopicOut(BaseModel):
    slug: str
    title_ru: str
    title_ka: str
    icon: str
    total: int
    learned: int
    has_lesson: bool


class StickerOut(BaseModel):
    word: WordOut
    learned: bool


class MeOut(BaseModel):
    child: ChildOut
    settings: SettingsOut
    week: WeekOut
    topics: list[TopicOut]
    stickers: list[StickerOut]
