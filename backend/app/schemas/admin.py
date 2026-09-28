"""Wire shapes of /api/admin/*: what the back office sees. No ORM objects cross this line."""

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.parent import WeekBrief


class ChildSummary(BaseModel):
    id: int
    name: str
    learned_words: int
    last_study_date: date | None
    # None = no coins earned that week.
    this_week: WeekBrief | None
    last_week: WeekBrief | None
    cap_reached: bool


class ParentRow(BaseModel):
    id: int
    telegram_id: int
    name: str | None
    created_at: datetime
    # The most recent lesson among the children; None = nobody has played yet.
    last_study_date: date | None
    children: list[ChildSummary]


class TopicProgressBrief(BaseModel):
    slug: str
    icon: str
    title_ru: str
    learned: int
    total: int
    # The child has seen at least one word of the topic (learned may still be 0).
    started: bool


class StudyDayOut(BaseModel):
    day: date
    finished: bool


class DeviceRow(BaseModel):
    id: int
    name: str | None
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None


class ChildCard(BaseModel):
    id: int
    name: str
    created_at: datetime
    # "WORD-1234" and the login link; None until a code has been issued.
    code: str | None
    login_url: str | None
    rate: int
    cap_lari: int
    show_hint: bool
    learned_words: int
    topics: list[TopicProgressBrief]
    # Days with a lesson over the last 28 days, oldest first.
    study_days: list[StudyDayOut]
    first_try_pct: int | None
    # Last six weeks with any coins row, newest first.
    weeks: list[WeekBrief]
    devices: list[DeviceRow]


class ParentCard(BaseModel):
    id: int
    telegram_id: int
    name: str | None
    created_at: datetime
    children: list[ChildCard]
