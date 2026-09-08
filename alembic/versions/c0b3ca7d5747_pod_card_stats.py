"""Pod card stats: per-event card facts + public_pod_card_stats and public_pod_archetype_stats

Revision ID: c0b3ca7d5747
Revises: tr4nscr1pt5ep
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c0b3ca7d5747"
down_revision: Union[str, None] = "tr4nscr1pt5ep"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CARD_VIEW_SQL = """
CREATE VIEW public_pod_card_stats AS
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
card_rows AS (
    SELECT
        c.set_code, c.card_name, c.card_set, c.colors, c.rarity, c.cmc, c.type_line,
        c.seen_count, c.last_seen_sum, c.saw_count, c.pick_num, c.maindecked, c.event_id, c.seat,
        COALESCE(s.code, 'UNKNOWN') AS season
    FROM pod_card_stats c
    JOIN pod_draft_events pde ON pde.id = c.event_id
    LEFT JOIN sets s ON pde.event_date BETWEEN s.start_date AND COALESCE(s.end_date, DATE '9999-12-31')
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

_ARCHETYPE_VIEW_SQL = """
CREATE VIEW public_pod_archetype_stats AS
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
        part.deck_colors,
        COALESCE(s.code, 'UNKNOWN') AS season,
        COALESCE(sg.game_wins, 0) AS game_wins,
        COALESCE(sg.games, 0) AS games
    FROM pod_draft_participants part
    JOIN pod_draft_events pde ON pde.id = part.event_id
    LEFT JOIN sets s ON pde.event_date BETWEEN s.start_date AND COALESCE(s.end_date, DATE '9999-12-31')
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
    op.create_table(
        "pod_card_stats",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("card_index", sa.Integer(), nullable=False),
        sa.Column("card_name", sa.String(), nullable=False),
        sa.Column("set_code", sa.String(), nullable=False),
        sa.Column("card_set", sa.String(), nullable=True),
        sa.Column("colors", sa.String(), nullable=True),
        sa.Column("rarity", sa.String(), nullable=True),
        sa.Column("cmc", sa.Float(), nullable=True),
        sa.Column("type_line", sa.String(), nullable=True),
        sa.Column("seat", sa.Integer(), nullable=True),
        sa.Column("pick_num", sa.Integer(), nullable=True),
        sa.Column("maindecked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column("last_seen_sum", sa.Integer(), nullable=False),
        sa.Column("saw_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["pod_draft_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", "card_index"),
    )
    op.create_index("ix_pod_card_stats_set", "pod_card_stats", ["set_code"])
    op.create_index("ix_pod_card_stats_set_card", "pod_card_stats", ["set_code", "card_name"])
    op.execute(_CARD_VIEW_SQL)
    op.execute(_ARCHETYPE_VIEW_SQL)
    op.execute("GRANT SELECT ON public_pod_card_stats TO anon;")
    op.execute("GRANT SELECT ON public_pod_archetype_stats TO anon;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_pod_archetype_stats;")
    op.execute("DROP VIEW IF EXISTS public_pod_card_stats;")
    op.drop_index("ix_pod_card_stats_set_card", table_name="pod_card_stats")
    op.drop_index("ix_pod_card_stats_set", table_name="pod_card_stats")
    op.drop_table("pod_card_stats")
