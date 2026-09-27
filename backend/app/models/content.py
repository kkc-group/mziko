"""Topics and words. Loaded from content/topics/*.yaml by `python -m app.seed`."""

import enum
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPK


class ImageKind(enum.StrEnum):
    emoji = "emoji"
    color = "color"
    file = "file"
    # No picture: the value (a letter or a word) is rendered as large Georgian text.
    text = "text"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[IntPK]
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    title_ka: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str] = mapped_column(String(16), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)

    words: Mapped[list["Word"]] = relationship(
        back_populates="topic", order_by="Word.order", cascade="all, delete-orphan"
    )


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (UniqueConstraint("topic_id", "slug"),)

    id: Mapped[IntPK]
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(50), nullable=False)
    ka: Mapped[str] = mapped_column(String(100), nullable=False)
    tr: Mapped[str] = mapped_column(String(100), nullable=False)
    ru: Mapped[str] = mapped_column(String(100), nullable=False)
    image_kind: Mapped[ImageKind] = mapped_column(
        Enum(ImageKind, name="image_kind", native_enum=True), nullable=False
    )
    image_value: Mapped[str] = mapped_column(String(255), nullable=False)
    # Letters only: an example word starting with the letter, shown on the intro card.
    # Shape: {"ka": ..., "tr": ..., "ru": ..., "emoji": ... | null}, see app.seed.AnchorSpec.
    anchor: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Position within the topic; equals the index in the YAML file.
    order: Mapped[int] = mapped_column(Integer, nullable=False)

    topic: Mapped[Topic] = relationship(back_populates="words")
