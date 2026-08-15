"""Index pod child tables on event_id

Revision ID: 8f9f8aab700b
Revises: t3w1n5p0dtr0
Create Date: 2026-08-15

public_pod_draft_events runs a correlated subquery per event for the champion, the seat count and
the round count. Without these both child tables were scanned in full each time, so the view cost
grew as events times seats: 68 ms warm on prod for 137 rows, against 2.3 ms for the 229k-row
leaderboard. The partial uq_pod_participant_event_player cannot serve a plain event_id lookup.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "8f9f8aab700b"
down_revision: Union[str, None] = "t3w1n5p0dtr0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_pod_draft_matches_event", "pod_draft_matches", ["event_id"], unique=False)
    op.create_index("ix_pod_draft_participants_event", "pod_draft_participants", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pod_draft_participants_event", table_name="pod_draft_participants")
    op.drop_index("ix_pod_draft_matches_event", table_name="pod_draft_matches")
