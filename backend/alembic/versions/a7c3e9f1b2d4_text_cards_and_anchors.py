"""text cards and letter anchors

Revision ID: a7c3e9f1b2d4
Revises: 6d7e19e4445d
Create Date: 2026-09-27 09:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c3e9f1b2d4"
down_revision: str | None = "6d7e19e4445d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A fourth kind of card: no picture, the value is rendered as large Georgian text.
    op.execute("ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'text'")
    op.add_column(
        "words",
        sa.Column("anchor", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("words", "anchor")
    # PostgreSQL cannot drop a single enum value; rebuild the type without 'text'.
    op.execute("DELETE FROM words WHERE image_kind = 'text'")
    op.execute("ALTER TYPE image_kind RENAME TO image_kind_old")
    op.execute("CREATE TYPE image_kind AS ENUM ('emoji', 'color', 'file')")
    op.execute(
        "ALTER TABLE words ALTER COLUMN image_kind TYPE image_kind "
        "USING image_kind::text::image_kind"
    )
    op.execute("DROP TYPE image_kind_old")
