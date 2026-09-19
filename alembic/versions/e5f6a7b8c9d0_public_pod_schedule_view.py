"""Add pod_calendar_days + public_pod_calendar view

The resolved pod format calendar the site renders, rebuilt by the schedule tick from the same
planned_on/championship logic that draws the Discord card. One row per day with ordered display
entries and an optional band flag (arrival / championship).

Revision ID: e5f6a7b8c9d0
Revises: a3lcq0d1e2f3
Create Date: 2026-09-19 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "a3lcq0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pod_calendar_days",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("entries", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("band", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("day"),
    )
    op.execute("""
        CREATE OR REPLACE VIEW public_pod_calendar AS
        SELECT day, entries, band
        FROM pod_calendar_days
        WHERE day >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY day ASC;
    """)
    op.execute("GRANT SELECT ON public_pod_calendar TO anon;")
    op.execute("GRANT SELECT ON public_pod_calendar TO authenticated;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_pod_calendar;")
    op.drop_table("pod_calendar_days")
