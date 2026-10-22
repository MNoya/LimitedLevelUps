"""Show Fantasy participants, their join time and their picks' flags before picks lock

Revision ID: c3f5a7e9b1d2
Revises: b8d2f4a6c1e3
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3f5a7e9b1d2"
down_revision: Union[str, None] = "b8d2f4a6c1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STANDINGS_COLUMNS = """
       m.event_code,
       left(encode(sha256(m.user_id::text::bytea), 'hex'), 16) AS member_key,
       (m.user_id::text = (nullif(current_setting('request.jwt.claims', true), '')::json->>'sub')) AS is_me,
       coalesce(v.name, 'Anonymous entrant') AS name,
       v.avatar_url,
       m.points, m.bracket_points, m.champion_called,
       rank() OVER (
           PARTITION BY m.event_code
           ORDER BY m.points DESC, m.champion_called DESC, m.lineup_saved_at ASC NULLS LAST
       )::int AS rank"""

STANDINGS_FROM = """
FROM fantasy_member_scores m
JOIN fantasy_events e ON e.code = m.event_code
LEFT JOIN fantasy_members v ON v.user_id = m.user_id"""

JOINED_AT_COLUMN = """,
       (SELECT min(p.created_at) FROM fantasy_picks p
        WHERE p.user_id = m.user_id AND p.event_code = m.event_code) AS joined_at"""


LINEUP_FLAGS_SQL = """
CREATE VIEW public_fantasy_lineup_flags AS
SELECT p.event_code,
       left(encode(sha256(p.user_id::text::bytea), 'hex'), 16) AS member_key,
       p.slot,
       f.country_code
FROM fantasy_picks p
JOIN fantasy_players f ON f.event_code = p.event_code AND f.id = p.player_id
WHERE p.from_round = 1
"""


def upgrade() -> None:
    columns = STANDINGS_COLUMNS + JOINED_AT_COLUMN
    op.execute(f"CREATE OR REPLACE VIEW public_fantasy_standings AS SELECT{columns}{STANDINGS_FROM}")
    op.execute(LINEUP_FLAGS_SQL)
    op.execute(_site_grant_sql("public_fantasy_lineup_flags"))


def downgrade() -> None:
    op.execute("DROP VIEW public_fantasy_lineup_flags")
    op.execute("DROP VIEW public_fantasy_standings")
    op.execute(
        f"CREATE VIEW public_fantasy_standings AS SELECT{STANDINGS_COLUMNS}{STANDINGS_FROM}"
        "\nWHERE now() >= e.picks_lock_at"
    )
    op.execute(_site_grant_sql("public_fantasy_standings"))


def _site_grant_sql(view: str) -> str:
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                GRANT SELECT ON {view} TO anon, authenticated;
            END IF;
        END $$;
    """
