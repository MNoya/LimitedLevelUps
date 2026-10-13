"""Fantasy subs close at the scheduled Day 2 start

Revision ID: f4n7d4y2l0ck
Revises: f4n7w1nd0w5d
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f4n7d4y2l0ck"
down_revision: Union[str, None] = "f4n7w1nd0w5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(_pick_window_function("AND p_at < e.picks_lock_at + interval '1 day'"))


def downgrade() -> None:
    op.execute(_pick_window_function(""))


def _pick_window_function(day_two_start_check: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION fantasy_pick_window_open(p_event text, p_from_round int, p_at timestamptz)
        RETURNS boolean
        LANGUAGE sql
        STABLE SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT CASE
                WHEN p_from_round = 1 THEN p_at < e.picks_lock_at
                WHEN p_from_round = e.cut_round + 1 THEN
                    p_at >= e.picks_lock_at {day_two_start_check}
                    AND (e.day_two_started_at IS NULL OR p_at < e.day_two_started_at)
                ELSE false
            END
            FROM fantasy_events e
            WHERE e.code = p_event
        $$
    """
