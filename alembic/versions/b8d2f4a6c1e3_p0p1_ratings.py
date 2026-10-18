"""P0P1 ratings snapshots the bot captures at the midway and scoring dates

Revision ID: b8d2f4a6c1e3
Revises: a7c3e9f1b2d4
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b8d2f4a6c1e3"
down_revision: Union[str, None] = "a7c3e9f1b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "p0p1_ratings",
        sa.Column("set_code", sa.Text(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("date_start", sa.Date(), nullable=False),
        sa.Column("date_end", sa.Date(), nullable=False),
        sa.Column("cards", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("phase IN ('midway', 'final')", name="ck_p0p1_ratings_phase"),
        sa.PrimaryKeyConstraint("set_code", "phase"),
    )
    op.execute("ALTER TABLE p0p1_ratings ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE VIEW public_p0p1_ratings AS
        SELECT set_code, phase, date_start, date_end, cards
        FROM p0p1_ratings;
    """)
    op.execute("GRANT SELECT ON public_p0p1_ratings TO anon, authenticated;")


def downgrade() -> None:
    op.execute("DROP VIEW public_p0p1_ratings;")
    op.drop_table("p0p1_ratings")
