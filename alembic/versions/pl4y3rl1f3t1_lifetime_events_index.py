"""Index draft_events for the lifetime profile's per-player history

Revision ID: pl4y3rl1f3t1
Revises: tr4ck3rgr4nt
Create Date: 2026-08-26

The lifetime profile pages one player's whole event log newest-first across every set. The existing
indexes lead with set_id, so that read fell back to a scan and sort. This orders on (player_id,
finished_at DESC, id) so the page reads straight off the index.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "pl4y3rl1f3t1"
down_revision: Union[str, None] = "tr4ck3rgr4nt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_draft_events_player_recent "
        "ON draft_events (player_id, finished_at DESC NULLS LAST, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_draft_events_player_recent")
