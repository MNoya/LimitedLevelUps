"""Expose a Set Championship's frozen seeds and RSVP answers so the site can show it before it is drafted

Revision ID: e5b7c9d1f3a4
Revises: d4a6b8c0e2f3
Create Date: 2026-10-22
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e5b7c9d1f3a4"
down_revision: Union[str, None] = "d4a6b8c0e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AVATAR_URL_SQL = """\
CASE WHEN p.avatar_hash IS NOT NULL AND p.discord_id IS NOT NULL
    THEN 'https://cdn.discordapp.com/avatars/' || p.discord_id || '/' || p.avatar_hash || '.png?size=128'
    ELSE NULL
END"""


def upgrade() -> None:
    op.execute(f"""
        CREATE VIEW public_pod_championship_seeds AS
        SELECT
            pcs.event_id,
            pde.set_code,
            pde.event_time,
            pcs.rank,
            COALESCE(p.display_name, pcs.display_name) AS display_name,
            p.slug                                     AS player_slug,
            {_AVATAR_URL_SQL}                          AS avatar_url,
            pcs.score,
            pcs.trophies,
            pcs.wildcard,
            pcs.created_at                             AS frozen_at
        FROM pod_championship_seeds pcs
        JOIN pod_draft_events pde ON pde.id = pcs.event_id
        LEFT JOIN players p ON p.id = pcs.player_id;
    """)
    op.execute(f"""
        CREATE VIEW public_pod_championship_rsvps AS
        SELECT
            ps.event_id,
            COALESCE(p.display_name, psm.display_name) AS display_name,
            p.slug                                     AS player_slug,
            {_AVATAR_URL_SQL}                          AS avatar_url,
            psm.rsvp,
            psm.confirmed_at IS NOT NULL               AS confirmed,
            psm.created_at                             AS answered_at
        FROM pod_signal_members psm
        JOIN pod_signals ps ON ps.id = psm.signal_id
        JOIN pod_draft_events pde ON pde.id = ps.event_id
        LEFT JOIN players p ON p.discord_id = psm.discord_user_id
        WHERE EXISTS (SELECT FROM pod_championship_seeds pcs WHERE pcs.event_id = pde.id);
    """)
    _grant_readers("public_pod_championship_seeds")
    _grant_readers("public_pod_championship_rsvps")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_pod_championship_rsvps")
    op.execute("DROP VIEW IF EXISTS public_pod_championship_seeds")


def _grant_readers(view: str) -> None:
    for role in ("anon", "authenticated"):
        op.execute(f"""
            DO $$
            BEGIN
                IF to_regclass('public.{view}') IS NOT NULL
                   AND EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'GRANT SELECT ON public.{view} TO {role}';
                END IF;
            END $$;
        """)
