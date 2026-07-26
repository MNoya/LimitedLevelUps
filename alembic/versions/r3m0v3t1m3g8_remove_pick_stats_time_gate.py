"""Remove hardcoded time gate from public_p0p1_pick_stats view

Revision ID: r3m0v3t1m3g8
Revises: t1r2o3p4h5y6
Create Date: 2026-07-24

The WHERE now() > '2026-06-23T15:00:00Z' clause was an MSH-specific gate.
Enforcement now lives in the frontend (useP0P1Ballot gates on isPastDeadline).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "r3m0v3t1m3g8"
down_revision: Union[str, None] = "t1r2o3p4h5y6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW public_p0p1_pick_stats AS
        WITH slot_counts AS (
            SELECT set_code, COUNT(DISTINCT slot) AS total_slots
            FROM p0p1_entries
            GROUP BY set_code
        ),
        complete_entrants AS (
            SELECT e.user_id, e.set_code
            FROM p0p1_entries e
            JOIN slot_counts s USING (set_code)
            GROUP BY e.user_id, e.set_code, s.total_slots
            HAVING COUNT(*) = s.total_slots
        )
        SELECT
            e.set_code,
            e.slot,
            e.card_name,
            COUNT(*)::int AS pick_count,
            ROUND(COUNT(*)::numeric * 100.0 /
                NULLIF(SUM(COUNT(*)) OVER (PARTITION BY e.set_code, e.slot), 0), 1
            ) AS pick_pct
        FROM p0p1_entries e
        JOIN complete_entrants c USING (user_id, set_code)
        GROUP BY e.set_code, e.slot, e.card_name;
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW public_p0p1_pick_stats AS
        WITH slot_counts AS (
            SELECT set_code, COUNT(DISTINCT slot) AS total_slots
            FROM p0p1_entries
            GROUP BY set_code
        ),
        complete_entrants AS (
            SELECT e.user_id, e.set_code
            FROM p0p1_entries e
            JOIN slot_counts s USING (set_code)
            GROUP BY e.user_id, e.set_code, s.total_slots
            HAVING COUNT(*) = s.total_slots
        )
        SELECT
            e.set_code,
            e.slot,
            e.card_name,
            COUNT(*)::int AS pick_count,
            ROUND(COUNT(*)::numeric * 100.0 /
                NULLIF(SUM(COUNT(*)) OVER (PARTITION BY e.set_code, e.slot), 0), 1
            ) AS pick_pct
        FROM p0p1_entries e
        JOIN complete_entrants c USING (user_id, set_code)
        WHERE now() > '2026-06-23T15:00:00Z'
        GROUP BY e.set_code, e.slot, e.card_name;
    """)
