"""Wire shapes of /api/parent/*: what the Telegram bot sees. No ORM objects cross this line."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.lesson import Lari

# Choices the bot offers as buttons; the API rejects anything else.
RATE_OPTIONS = (5, 10, 15, 20, 30)
CAP_OPTIONS = (5, 10, 15, 20, 30)

WeekStatusOut = Literal["open", "paid"]


NAME_MAX = 100  # parents.name and children.name are String(100)


class ChildInfo(BaseModel):
    id: int
    name: str
    rate: int
    cap_lari: int
    show_hint: bool


class ParentOut(BaseModel):
    """The parent behind a Telegram id, as the registration wizard sees them."""

    telegram_id: int
    name: str | None
    children: list[ChildInfo]


class ParentRegister(BaseModel):
    name: str = Field(max_length=NAME_MAX)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class WordBrief(BaseModel):
    ka: str
    tr: str
    ru: str
    icon: str  # the emoji, or the word itself when it has no emoji


class WeekBrief(BaseModel):
    id: int
    week_start: date
    week_end: date
    coins: int
    status: WeekStatusOut
    lari_due: Lari  # what the coins are worth at the child's current rate and cap
    lari_paid: Lari | None = None
    paid_at: datetime | None = None


class WeekReportOut(BaseModel):
    child: ChildInfo
    week: WeekBrief
    days_studied: int
    learned: list[WordBrief]
    cap_reached: bool
    unpaid_past: list[WeekBrief]


class PayOut(BaseModel):
    already_paid: bool
    report: WeekReportOut


class ChildCreate(BaseModel):
    name: str = Field(max_length=NAME_MAX)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class ChildAttach(BaseModel):
    """The login code of an existing child, e.g. "LOMI-7241"."""

    code: str = Field(pattern=r"^\s*[A-Za-z]{4}-?\d{4}\s*$")


class SettingsPatch(BaseModel):
    rate: int | None = None
    cap_lari: int | None = None
    show_hint: bool | None = None

    @field_validator("rate")
    @classmethod
    def rate_is_an_option(cls, value: int | None) -> int | None:
        if value is not None and value not in RATE_OPTIONS:
            raise ValueError(f"rate must be one of {RATE_OPTIONS}")
        return value

    @field_validator("cap_lari")
    @classmethod
    def cap_is_an_option(cls, value: int | None) -> int | None:
        if value is not None and value not in CAP_OPTIONS:
            raise ValueError(f"cap must be one of {CAP_OPTIONS}")
        return value


class WordProgressOut(BaseModel):
    ka: str
    ru: str
    stage: int
    # The last day the stage grew (Asia/Tbilisi); None until the first correct answer.
    last_correct_date: date | None = None
    # Shown on a lesson at least once, and the Tbilisi day it first was: a word
    # can be "in work" at stage 0 when the first-try answer was wrong.
    introduced: bool = False
    introduced_on: date | None = None


class TopicProgressOut(BaseModel):
    slug: str
    section: Literal["letters", "syllables", "words"]
    icon: str
    title_ru: str
    learned: int
    total: int
    words: list[WordProgressOut]


class ProgressOut(BaseModel):
    child: ChildInfo
    topics: list[TopicProgressOut]
    # Lessons played to the end ("Ура, занятие готово!"), all time.
    lessons_done: int = 0


class ChildCodeOut(BaseModel):
    word: str
    pin: str
    code: str  # e.g. "LOMI-7241"
    url: str


class DeviceOut(BaseModel):
    id: int
    name: str | None
    created_at: datetime
    last_seen_at: datetime | None


class DueReportOut(BaseModel):
    telegram_ids: list[int]
    report: WeekReportOut
