"""Pod card/archetype season: resolve each pod date to one closed-window set

Revision ID: f7a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f7a1b2c3d4e5"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEASON_LATERAL = """
    LEFT JOIN LATERAL (
        SELECT sq.code
        FROM sets sq
        WHERE sq.end_date IS NOT NULL
          AND pde.event_date BETWEEN sq.start_date AND sq.end_date
        ORDER BY sq.start_date DESC
        LIMIT 1
    ) s ON true
"""

_SEASON_OVERLAP = """
    LEFT JOIN sets s ON pde.event_date BETWEEN s.start_date AND COALESCE(s.end_date, DATE '9999-12-31')
"""

_MATCH_AND_SEATS = """
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
"""


def _card_view_sql(season_join: str) -> str:
    return f"""
CREATE OR REPLACE VIEW public_pod_card_stats AS
{_MATCH_AND_SEATS}
card_rows AS (
    SELECT
        c.set_code, c.card_name, c.card_set, c.colors, c.rarity, c.cmc, c.type_line,
        c.seen_count, c.last_seen_sum, c.saw_count, c.pick_num, c.maindecked, c.event_id, c.seat,
        COALESCE(s.code, 'UNKNOWN') AS season
    FROM pod_card_stats c
    JOIN pod_draft_events pde ON pde.id = c.event_id
{season_join}
),
sightings AS (
    SELECT
        set_code, season, card_name,
        max(card_set) AS card_set,
        max(colors) AS colors,
        max(rarity) AS rarity,
        max(cmc) AS cmc,
        max(type_line) AS type_line,
        sum(seen_count)::int AS seen_count,
        sum(last_seen_sum)::int AS last_seen_sum,
        sum(saw_count)::int AS saw_count,
        count(*) FILTER (WHERE pick_num IS NOT NULL)::int AS pick_count,
        sum(pick_num) FILTER (WHERE pick_num IS NOT NULL)::int AS pick_sum,
        count(*) FILTER (WHERE maindecked)::int AS maindeck_count,
        count(DISTINCT event_id)::int AS drafts
    FROM card_rows
    GROUP BY set_code, season, card_name
),
maindeck_seats AS (
    SELECT DISTINCT set_code, season, card_name, event_id, seat
    FROM card_rows
    WHERE maindecked AND seat IS NOT NULL
),
maindeck_games AS (
    SELECT
        md.set_code, md.season, md.card_name,
        sum(COALESCE(sg.games, 0))::int AS game_count,
        sum(COALESCE(sg.game_wins, 0))::int AS game_wins
    FROM maindeck_seats md
    LEFT JOIN seat_games sg ON sg.event_id = md.event_id AND sg.seat = md.seat
    GROUP BY md.set_code, md.season, md.card_name
)
SELECT
    s.set_code, s.season, s.card_name, s.card_set, s.colors, s.rarity, s.cmc, s.type_line,
    s.seen_count, s.last_seen_sum, s.saw_count, s.pick_count, s.pick_sum, s.maindeck_count, s.drafts,
    COALESCE(g.game_count, 0) AS game_count,
    COALESCE(g.game_wins, 0) AS game_wins
FROM sightings s
LEFT JOIN maindeck_games g USING (set_code, season, card_name);
"""


def _archetype_view_sql(season_join: str) -> str:
    return f"""
CREATE OR REPLACE VIEW public_pod_archetype_stats AS
{_MATCH_AND_SEATS}
deck_rows AS (
    SELECT
        pde.set_code,
        part.deck_colors,
        COALESCE(s.code, 'UNKNOWN') AS season,
        COALESCE(sg.game_wins, 0) AS game_wins,
        COALESCE(sg.games, 0) AS games
    FROM pod_draft_participants part
    JOIN pod_draft_events pde ON pde.id = part.event_id
{season_join}
    LEFT JOIN seat_games sg ON sg.event_id = part.event_id AND sg.seat = part.seat_index
    WHERE part.deck_colors IS NOT NULL AND part.deck_colors <> ''
)
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
    op.execute(_card_view_sql(_SEASON_LATERAL))
    op.execute(_archetype_view_sql(_SEASON_LATERAL))


def downgrade() -> None:
    op.execute(_card_view_sql(_SEASON_OVERLAP))
    op.execute(_archetype_view_sql(_SEASON_OVERLAP))
