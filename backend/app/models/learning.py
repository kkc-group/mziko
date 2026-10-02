"""Per-child word progress, lesson sessions and answers."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IntPK
from app.models.content import Topic, Word
from app.models.people import Child


class WordProgress(Base):
    """Spaced-repetition state of one word for one child.

    `stage` grows by one per calendar day (Asia/Tbilisi) with a first-try correct
    answer; stage 3 means the word is learned.
    """

    __tablename__ = "word_progress"
    __table_args__ = (
        UniqueConstraint("child_id", "word_id"),
        CheckConstraint("stage BETWEEN 0 AND 3", name="stage_range"),
    )

    id: Mapped[IntPK]
    child_id: Mapped[int] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    last_correct_date: Mapped[date | None] = mapped_column(Date)
    introduced: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Tbilisi day the word was first shown.
    introduced_on: Mapped[date | None] = mapped_column(Date)
    learned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    child: Mapped[Child] = relationship()
    word: Mapped[Word] = relationship()


class Session(Base):
    """One lesson. `steps` is the server-generated plan the client walks through."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[int] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # None for a review-only session (every lesson is done).
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    # Calendar day in Asia/Tbilisi when the session was started.
    study_date: Mapped[date] = mapped_column(Date, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[CreatedAt]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    child: Mapped[Child] = relationship()
    topic: Mapped[Topic | None] = relationship()
    answers: Mapped[list["Answer"]] = relationship(back_populates="session")


class Answer(Base):
    """A submitted answer. `client_answer_id` makes retries idempotent."""

    __tablename__ = "answers"

    id: Mapped[IntPK]
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # The word the child picked (not necessarily the correct one).
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    coins_gained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_learned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[CreatedAt]

    session: Mapped[Session] = relationship(back_populates="answers")


class TopicAccess(Base):
    """A parent's say on one topic for one child, set from the cabinet.

    No row means the topic follows the usual order. "open" lets the child start
    it at once, past the order and the one-new-topic-a-day limit; "closed" locks
    it whatever its progress.
    """

    __tablename__ = "topic_access"
    __table_args__ = (CheckConstraint("mode IN ('open', 'closed')", name="mode_known"),)

    child_id: Mapped[int] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(6), nullable=False)
