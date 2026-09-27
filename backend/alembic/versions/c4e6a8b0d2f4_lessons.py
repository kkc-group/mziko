"""lessons: when a word was introduced, review-only sessions without a topic

Revision ID: c4e6a8b0d2f4
Revises: a7c3e9f1b2d4
Create Date: 2026-09-27 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e6a8b0d2f4"
down_revision: str | None = "a7c3e9f1b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The Tbilisi day a word was first shown: "one new topic per day" is decided by it.
    op.add_column("word_progress", sa.Column("introduced_on", sa.Date(), nullable=True))
    # A session made only of reviews (every lesson done) belongs to no topic.
    op.alter_column("sessions", "topic_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM sessions WHERE topic_id IS NULL")
    op.alter_column("sessions", "topic_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("word_progress", "introduced_on")
