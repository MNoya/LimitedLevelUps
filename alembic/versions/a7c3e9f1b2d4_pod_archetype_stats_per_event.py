"""Pod archetype stats per event, so the pods page can scope Top Colors to the events it lists

Revision ID: a7c3e9f1b2d4
Revises: f4n7d4y2l0ck
Create Date: 2026-10-18
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a7c3e9f1b2d4"
down_revision: Union[str, None] = "f4n7d4y2l0ck"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DECK_ROWS = """
WITH match_sides AS (
    SELECT m.event_id, m.player_a_name AS name,
           CASE WHEN m.winner_name = m.player_a_name
                THEN split_part(m.score, '-', 1)::int ELSE split_part(m.score, '-', 2)::int END AS game_wins,
           split_part(m.score, '-', 1)::int + split_part(m.score, '-', 2)::int AS games
    FROM pod_draft_matches m
    WHERE m.winner_name IS NOT NULL AND m.winner_name <> '(skipped)' AND m.score ~ '^[0-9]+-[0-9]+$'
    UNION ALL
    SELECT m.event_id, m.player_b_name AS name,
           CASE WHEN m.winner_name = m.player_b_name
                THEN split_part(m.score, '-', 1)::int ELSE split_part(m.score, '-', 2)::int END AS game_wins,
           split_part(m.score, '-', 1)::int + split_part(m.score, '-', 2)::int AS games
    FROM pod_draft_matches m
    WHERE m.winner_name IS NOT NULL AND m.winner_name <> '(skipped)' AND m.score ~ '^[0-9]+-[0-9]+$'
),
seat_games AS (
    SELECT ms.event_id, part.seat_index AS seat,
           SUM(ms.game_wins) AS game_wins, SUM(ms.games) AS games
    FROM match_sides ms
    JOIN pod_draft_participants part
      ON part.event_id = ms.event_id AND ms.name IN (part.display_name, part.draftmancer_name)
    WHERE part.seat_index IS NOT NULL
    GROUP BY ms.event_id, part.seat_index
),
deck_rows AS (
    SELECT
        pde.set_code,
        part.event_id,
        part.deck_colors,
        COALESCE(s.code, 'UNKNOWN') AS season,
        COALESCE(sg.game_wins, 0) AS game_wins,
        COALESCE(sg.games, 0) AS games
    FROM pod_draft_participants part
    JOIN pod_draft_events pde ON pde.id = part.event_id
    LEFT JOIN LATERAL (
        SELECT sq.code
        FROM sets sq
        WHERE sq.end_date IS NOT NULL
          AND pde.event_date BETWEEN sq.start_date AND sq.end_date
        ORDER BY sq.start_date DESC
        LIMIT 1
    ) s ON true
    LEFT JOIN seat_games sg ON sg.event_id = part.event_id AND sg.seat = part.seat_index
    WHERE part.deck_colors IS NOT NULL AND part.deck_colors <> ''
)
"""

_PER_EVENT_VIEW = f"""
CREATE OR REPLACE VIEW public_pod_archetype_stats AS
{_DECK_ROWS}
SELECT
    set_code,
    season,
    deck_colors,
    count(*)::int AS decks,
    sum(game_wins)::int AS game_wins,
    sum(games)::int AS games,
    event_id
FROM deck_rows
GROUP BY set_code, season, deck_colors, event_id;
"""

_PER_SEASON_VIEW = f"""
CREATE VIEW public_pod_archetype_stats AS
{_DECK_ROWS}
SELECT
    set_code,
    season,
    deck_colors,
    count(*)::int AS decks,
    sum(game_wins)::int AS game_wins,
    sum(games)::int AS games
FROM deck_rows
GROUP BY set_code, season, deck_colors;
"""


def upgrade() -> None:
    op.execute(_PER_EVENT_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW public_pod_archetype_stats;")
    op.execute(_PER_SEASON_VIEW)
    op.execute("GRANT SELECT ON public_pod_archetype_stats TO anon, authenticated;")
