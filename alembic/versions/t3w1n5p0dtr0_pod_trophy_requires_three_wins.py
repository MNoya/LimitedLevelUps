"""A pod trophy is three match wins, never a pod win by placement

A four or six player pod cannot produce a 3-0, so its 2-1 winner was banking a trophy and five points
the same board pays for an 8-player 3-0. Placement drops out of the trophy rule everywhere: a 2-1 pod
win now buckets as a two-win finish, and a 3-0 that placed second in a ten-player pod still counts.

Revision ID: t3w1n5p0dtr0
Revises: a7f1c3e5b9d2
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op


revision: str = "t3w1n5p0dtr0"
down_revision: Union[str, None] = "a7f1c3e5b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WINS_SQL = "COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int"
_LOSSES_SQL = "COALESCE(NULLIF(split_part(pdp.record, '-', 2), ''), '0')::int"
_POD_SLUG_SQL = "trim(both '-' from regexp_replace(lower(pde.name), '[^a-z0-9]+', '-', 'g'))"

_AVATAR_URL_SQL = """\
CASE WHEN p.avatar_hash IS NOT NULL AND p.discord_id IS NOT NULL
    THEN 'https://cdn.discordapp.com/avatars/' || p.discord_id || '/' || p.avatar_hash || '.png?size=128'
    ELSE NULL
END"""

_TROPHY_NEW = f"{_WINS_SQL} >= 3"
_TROPHY_OLD = f"{_WINS_SQL} >= 3 OR pdp.placement = 1"

_FINISH_COLUMNS_NEW = f"""COUNT(*) FILTER (WHERE {_WINS_SQL} = 2)::int AS two_win_finishes,
            COUNT(*) FILTER (WHERE {_WINS_SQL} = 1)::int AS one_win_finishes,"""

_FINISH_COLUMNS_OLD = f"""COUNT(*) FILTER (
                WHERE {_WINS_SQL} = 2 AND pdp.placement IS DISTINCT FROM 1
            )::int AS two_win_finishes,
            COUNT(*) FILTER (
                WHERE {_WINS_SQL} = 1 AND pdp.placement IS DISTINCT FROM 1
            )::int AS one_win_finishes,"""


def upgrade() -> None:
    _apply(_TROPHY_NEW, _FINISH_COLUMNS_NEW, f"({_TROPHY_NEW})")


def downgrade() -> None:
    _apply(_TROPHY_OLD, _FINISH_COLUMNS_OLD, "(pdp.placement = 1 OR pdp.record = '3-0')")


def _apply(trophy_filter: str, finish_columns: str, event_is_trophy: str) -> None:
    op.execute(_player_events_view_sql(event_is_trophy))
    op.execute(_pod_scoring_sql(trophy_filter, finish_columns))
    op.execute(_player_pod_stats_sql(trophy_filter))
    for view in ("public_player_draft_events", "public_pod_scoring", "public_player_pod_stats"):
        _grant(view)


def _player_events_view_sql(pod_is_trophy: str) -> str:
    return f"""
        CREATE OR REPLACE VIEW public_player_draft_events AS
        SELECT
            p.slug,
            s.code AS set_code,
            de.id AS event_id,
            de.format,
            de.expansion,
            de.wins,
            de.losses,
            de.is_trophy,
            de.colors,
            de.started_at,
            de.finished_at,
            de.seventeenlands_event_id,
            CASE
                WHEN de.seventeenlands_event_id IS NOT NULL
                    THEN 'https://www.17lands.com/deck/' || de.seventeenlands_event_id
                ELSE NULL
            END AS external_url,
            NULL::text AS event_name,
            NULL::text AS pod_event_slug,
            de.end_rank
        FROM draft_events de
        JOIN players p ON p.id = de.player_id
        JOIN sets s ON s.id = de.set_id
        WHERE p.active = true

        UNION ALL

        SELECT
            p.slug,
            pde.set_code,
            pdp.id AS event_id,
            'PodDraft' AS format,
            pde.set_code AS expansion,
            {_WINS_SQL} AS wins,
            {_LOSSES_SQL} AS losses,
            {pod_is_trophy} AS is_trophy,
            COALESCE(pdp.deck_colors, '') AS colors,
            pde.event_time AS started_at,
            pde.event_time AS finished_at,
            NULL::text AS seventeenlands_event_id,
            NULL::text AS external_url,
            pde.name AS event_name,
            {_POD_SLUG_SQL} AS pod_event_slug,
            NULL::text AS end_rank
        FROM pod_draft_participants pdp
        JOIN pod_draft_events pde ON pde.id = pdp.event_id
        JOIN players p ON p.id = pdp.player_id
        WHERE p.active = true
          AND (pdp.placement IS NOT NULL OR pdp.record IS NOT NULL);
    """


def _pod_scoring_sql(trophy_filter: str, finish_columns: str) -> str:
    return f"""
        CREATE OR REPLACE VIEW public_pod_scoring AS
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


def _grant(view: str) -> None:
    for role in ("anon", "authenticated"):
        op.execute(f"""
            DO $$
            BEGIN
                IF to_regclass('public.{view}') IS NOT NULL
                   AND EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'GRANT SELECT ON {view} TO {role}';
                END IF;
            END
            $$;
        """)
