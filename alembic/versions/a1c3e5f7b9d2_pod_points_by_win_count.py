"""Bucket pod scoring by match wins instead of the record string

A pod finish is paid on how many matches the player won, so a 2-0 cut short by an opponent dropping
pays the same as a 2-1, and a one-win finish starts paying a half point. Replaces the wins_2_1 column
with two_win_finishes + one_win_finishes on public_pod_scoring, and re-keys the trophy filter off the
parsed win count so it no longer depends on the literal '3-0'.

Revision ID: a1c3e5f7b9d2
Revises: f4a9c2e51d78
Create Date: 2026-08-13
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, None] = "f4a9c2e51d78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AVATAR_URL_SQL = """\
CASE WHEN p.avatar_hash IS NOT NULL AND p.discord_id IS NOT NULL
    THEN 'https://cdn.discordapp.com/avatars/' || p.discord_id || '/' || p.avatar_hash || '.png?size=128'
    ELSE NULL
END"""

_WINS_SQL = "COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int"
_LOSSES_SQL = "COALESCE(NULLIF(split_part(pdp.record, '-', 2), ''), '0')::int"

_TROPHY_FILTER_NEW = f"{_WINS_SQL} >= 3 OR pdp.placement = 1"
_TROPHY_FILTER_OLD = "pdp.record = '3-0' OR pdp.placement = 1"


def _pod_scoring_sql(trophy_filter: str, finish_columns: str) -> str:
    return f"""
        CREATE VIEW public_pod_scoring AS
        SELECT
            p.slug,
            p.display_name,
            {_AVATAR_URL_SQL} AS avatar_url,
            pde.set_code,
            COUNT(*) FILTER (WHERE {trophy_filter})::int AS trophies,
            {finish_columns}
            COUNT(*)::int AS events,
            COALESCE(SUM({_WINS_SQL}), 0)::int AS wins,
            COALESCE(SUM({_LOSSES_SQL}), 0)::int AS losses,
            p.leaderboard_opt_in
        FROM pod_draft_participants pdp
        JOIN pod_draft_events pde ON pde.id = pdp.event_id
        JOIN players p ON p.id = pdp.player_id
        WHERE p.active = true
          AND pdp.record IS NOT NULL
        GROUP BY p.slug, p.display_name, p.avatar_hash, p.discord_id, pde.set_code, p.leaderboard_opt_in;
    """


def _player_pod_stats_sql(trophy_filter: str) -> str:
    return f"""
        CREATE OR REPLACE VIEW public_player_pod_stats AS
        SELECT
            pde.set_code,
            p.slug,
            p.display_name,
            {_AVATAR_URL_SQL} AS avatar_url,
            COUNT(*)::int AS events,
            COALESCE(SUM({_WINS_SQL}), 0)::int AS wins,
            COALESCE(SUM({_LOSSES_SQL}), 0)::int AS losses,
            COUNT(*) FILTER (WHERE {trophy_filter})::int AS trophies,
            MAX(pde.event_time) AS last_finished_at
        FROM pod_draft_participants pdp
        JOIN pod_draft_events pde ON pde.id = pdp.event_id
        JOIN players p ON p.id = pdp.player_id
        WHERE p.active = true AND pdp.record IS NOT NULL
        GROUP BY pde.set_code, p.slug, p.display_name, p.avatar_hash, p.discord_id;
    """


_FINISH_COLUMNS_NEW = f"""COUNT(*) FILTER (
                WHERE {_WINS_SQL} = 2 AND pdp.placement IS DISTINCT FROM 1
            )::int AS two_win_finishes,
            COUNT(*) FILTER (
                WHERE {_WINS_SQL} = 1 AND pdp.placement IS DISTINCT FROM 1
            )::int AS one_win_finishes,"""

_FINISH_COLUMNS_OLD = """COUNT(*) FILTER (
                WHERE pdp.record = '2-1' AND pdp.placement IS DISTINCT FROM 1
            )::int AS wins_2_1,"""


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_pod_scoring;")
    op.execute(_pod_scoring_sql(_TROPHY_FILTER_NEW, _FINISH_COLUMNS_NEW))
    op.execute(_player_pod_stats_sql(_TROPHY_FILTER_NEW))
    op.execute("GRANT SELECT ON public_pod_scoring TO anon, authenticated;")
    op.execute("GRANT SELECT ON public_player_pod_stats TO anon, authenticated;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_pod_scoring;")
    op.execute(_pod_scoring_sql(_TROPHY_FILTER_OLD, _FINISH_COLUMNS_OLD))
    op.execute(_player_pod_stats_sql(_TROPHY_FILTER_OLD))
    op.execute("GRANT SELECT ON public_pod_scoring TO anon, authenticated;")
    op.execute("GRANT SELECT ON public_player_pod_stats TO anon, authenticated;")
