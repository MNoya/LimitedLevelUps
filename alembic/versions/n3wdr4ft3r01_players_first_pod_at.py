"""Players carry the timestamp of their first finished pod, so a new drafter is one column read

Revision ID: n3wdr4ft3r01
Revises: 8f9f8aab700b
Create Date: 2026-08-17

Backfilled from the earliest pod each player finished with a record, falling back to the event date
for the pods that never got a finalized_at written.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n3wdr4ft3r01"
down_revision: Union[str, None] = "8f9f8aab700b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("first_pod_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("""
        UPDATE players SET first_pod_at = played.first_pod_at
        FROM (
            SELECT p.player_id, MIN(COALESCE(e.finalized_at, e.event_date::timestamptz)) AS first_pod_at
            FROM pod_draft_participants p
            JOIN pod_draft_events e ON e.id = p.event_id
            WHERE p.player_id IS NOT NULL AND p.record IS NOT NULL
            GROUP BY p.player_id
        ) AS played
        WHERE players.id = played.player_id
    """)


def downgrade() -> None:
    op.drop_column("players", "first_pod_at")
