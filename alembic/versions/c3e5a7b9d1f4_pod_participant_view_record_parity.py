"""Make the live record in public_pod_draft_event_participants agree with the stored one

The stored record is `played_record`: a forfeited bye is not a loss, so a player who dropped keeps
only the matches they played. The live fallback counted those forfeits as losses, so a running pod
showed a record that changed at finalize. It now excludes bye rows the same way.

Restores two columns d4e5f6g7h8i9 dropped when it rebuilt the view from an older copy:
draftmancer_name, and the mock-draft record CASE that keeps a mock's matchless roster off 0-0.

Revision ID: c3e5a7b9d1f4
Revises: b2d4f6a8c0e1
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3e5a7b9d1f4"
down_revision: Union[str, None] = "b2d4f6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AVATAR_URL_SQL = """\
CASE WHEN p.avatar_hash IS NOT NULL AND p.discord_id IS NOT NULL
    THEN 'https://cdn.discordapp.com/avatars/' || p.discord_id || '/' || p.avatar_hash || '.png?size=128'
    ELSE NULL
END"""


def _live_record_sql(*, byes_are_losses: bool) -> str:
    bye_filter = "" if byes_are_losses else "\n                  AND pdm.score IS DISTINCT FROM 'bye'"
    return f"""\
COALESCE(
    pdp.record,
    (
        SELECT (COUNT(*) FILTER (
                WHERE pdm.winner_name = pdp.draftmancer_name
            ))::text
            || '-'
            || (COUNT(*) FILTER (
                WHERE pdm.winner_name IS NOT NULL
                  AND pdm.winner_name <> pdp.draftmancer_name
                  AND pdm.winner_name <> '(skipped)'{bye_filter}
            ))::text
        FROM pod_draft_matches pdm
        WHERE pdm.event_id = pdp.event_id
          AND pdp.draftmancer_name IS NOT NULL
          AND (pdm.player_a_name = pdp.draftmancer_name OR pdm.player_b_name = pdp.draftmancer_name)
    )
)"""


def _recreate_view(*, byes_are_losses: bool, mock_aware: bool, with_draftmancer_name: bool) -> None:
    live_record = _live_record_sql(byes_are_losses=byes_are_losses)
    record_sql = f"CASE WHEN pde.kind = 'mock' THEN NULL ELSE {live_record} END" if mock_aware else live_record
    event_join = "LEFT JOIN pod_draft_events pde ON pde.id = pdp.event_id" if mock_aware else ""
    draftmancer_col = "pdp.draftmancer_name," if with_draftmancer_name else ""
    op.execute("DROP VIEW IF EXISTS public_pod_draft_event_participants;")
    op.execute(f"""
        CREATE VIEW public_pod_draft_event_participants AS
        SELECT
            pdp.event_id,
            pdp.display_name,
            {draftmancer_col}
            pdp.seat_index,
            pdp.placement,
            {record_sql}                    AS record,
            pdp.deck_colors,
            pdp.deck_screenshot_url,
            pdp.deck_screenshot_caption,
            p.slug                          AS player_slug,
            p.display_name                  AS player_display_name,
            {_AVATAR_URL_SQL}               AS avatar_url
        FROM pod_draft_participants pdp
        LEFT JOIN players p ON p.id = pdp.player_id
        {event_join};
    """)
    _grant_readers("public_pod_draft_event_participants")


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


def upgrade() -> None:
    _recreate_view(byes_are_losses=False, mock_aware=True, with_draftmancer_name=True)


def downgrade() -> None:
    _recreate_view(byes_are_losses=True, mock_aware=False, with_draftmancer_name=False)
