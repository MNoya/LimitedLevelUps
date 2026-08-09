"""public_sets board follows first results

Revision ID: b0a4d5e7f1ab
Revises: c0nf1rm5eat
Create Date: 2026-08-09

The board used to flip at noon ET on the Arena release date, which leaves the days of Early Access
and the paper prerelease pointing at the outgoing set while players are already logging results for
the new one. The next set now claims is_active as soon as its first result exists, from 17lands
aggregates or a /trophy self-report, and the set appears in the view from that moment too.

Mirrors resolve_board_set in bot/services/active_set.py — keep them in lockstep.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b0a4d5e7f1ab"
down_revision: Union[str, None] = "c0nf1rm5eat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BOARD_VIEW = """
    CREATE OR REPLACE VIEW public_sets AS
    WITH flagged AS (
        SELECT
            s.*,
            now() >= ((s.start_date + time '12:00') AT TIME ZONE 'America/New_York') AS released,
            (
                EXISTS (SELECT 1 FROM player_stats ps WHERE ps.set_id = s.id)
                OR EXISTS (SELECT 1 FROM self_reported_events se WHERE upper(se.set_code) = s.code)
            ) AS has_results
        FROM sets s
    ),
    next_up AS (
        SELECT code, has_results
        FROM flagged
        WHERE end_date IS NOT NULL AND NOT released
        ORDER BY start_date
        LIMIT 1
    ),
    board AS (
        SELECT COALESCE(
            (SELECT code FROM next_up WHERE has_results),
            (
                SELECT code FROM flagged
                WHERE end_date IS NOT NULL
                  AND released
                  AND now() < (((end_date + 1) + time '12:00') AT TIME ZONE 'America/New_York')
                ORDER BY start_date DESC
                LIMIT 1
            )
        ) AS code
    )
    SELECT
        f.code,
        f.name,
        f.start_date,
        f.end_date,
        (f.code = (SELECT code FROM board)) AS is_active,
        (NOT f.released) AS early,
        f.last_refreshed_at
    FROM flagged f
    WHERE f.start_date <= CURRENT_DATE OR f.has_results;
"""

RELEASE_DATE_VIEW = """
    CREATE OR REPLACE VIEW public_sets AS
    SELECT
        s.code,
        s.name,
        s.start_date,
        s.end_date,
        (
            s.end_date IS NOT NULL
            AND now() >= ((s.start_date + time '12:00') AT TIME ZONE 'America/New_York')
            AND now() <  (((s.end_date + 1) + time '12:00') AT TIME ZONE 'America/New_York')
        ) AS is_active,
        (now() < ((s.start_date + time '12:00') AT TIME ZONE 'America/New_York')) AS early,
        s.last_refreshed_at
    FROM sets s
    WHERE s.start_date <= CURRENT_DATE
       OR EXISTS (SELECT 1 FROM player_stats ps WHERE ps.set_id = s.id);
"""


def upgrade() -> None:
    op.execute(BOARD_VIEW)


def downgrade() -> None:
    op.execute(RELEASE_DATE_VIEW)
