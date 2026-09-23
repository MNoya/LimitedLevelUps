"""Add public_pod_card_decks: one row per drafted card per seat for the card detail view

Revision ID: a8b9c0d1e2f3
Revises: f7a1b2c3d4e5
Create Date: 2026-09-23
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
CREATE VIEW public_pod_card_decks AS
SELECT
    c.set_code,
    COALESCE(s.code, 'UNKNOWN') AS season,
    c.card_name,
    c.card_set,
    c.event_id,
    e.slug AS event_slug,
    e.name AS event_name,
    e.event_date,
    e.event_time,
    c.seat,
    (
        SELECT ((booster.ord - 1) / jsonb_array_length(raw.draft_log -> 'seats'))::int + 1
        FROM jsonb_array_elements(raw.draft_log -> 'packs') WITH ORDINALITY AS booster(cards, ord)
        WHERE booster.cards @> to_jsonb(c.card_index)
        LIMIT 1
    ) AS pack_num,
    c.pick_num,
    c.maindecked,
    p.display_name,
    p.player_slug,
    p.player_display_name,
    p.avatar_url,
    p.deck_colors,
    p.record,
    p.placement,
    p.deck_screenshot_url,
    p.deck_screenshot_caption
FROM pod_card_stats c
JOIN public_pod_draft_events e ON e.event_id = c.event_id
JOIN pod_draft_events raw ON raw.id = c.event_id
JOIN public_pod_draft_event_participants p ON p.event_id = c.event_id AND p.seat_index = c.seat
LEFT JOIN LATERAL (
    SELECT sq.code
    FROM sets sq
    WHERE sq.end_date IS NOT NULL
      AND e.event_date BETWEEN sq.start_date AND sq.end_date
    ORDER BY sq.start_date DESC
    LIMIT 1
) s ON true
WHERE c.pick_num IS NOT NULL
  AND e.kind <> 'mock'
  AND (e.is_finalized OR NOT e.closed_decklist);
""")
    op.execute("GRANT SELECT ON public_pod_card_decks TO anon;")
    op.execute("GRANT SELECT ON public_pod_card_decks TO authenticated;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_pod_card_decks;")
