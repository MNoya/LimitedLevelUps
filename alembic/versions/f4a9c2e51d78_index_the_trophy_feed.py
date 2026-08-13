"""Index the trophy feed so it stops sorting every trophy in the log

public_recent_trophies filters to trophies and orders by finish time, and the page's LIMIT sits
above that, so serving a board's feed sorted all 50,705 trophy rows. A partial index over just the
trophy rows, in the order the view asks for, lets the planner walk the feed instead.

Revision ID: f4a9c2e51d78
Revises: e3f8a1c72d64
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f4a9c2e51d78"
down_revision: Union[str, None] = "e3f8a1c72d64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_draft_events_trophy_feed
            ON draft_events (set_id, finished_at DESC NULLS LAST)
            WHERE is_trophy
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_draft_events_trophy_feed")
