"""draft_events.detail_checked_at

Revision ID: dt1ch3ck3d01
Revises: c4rdm3nt10n1
Create Date: 2026-10-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "dt1ch3ck3d01"
down_revision: Union[str, None] = "c4rdm3nt10n1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("draft_events", sa.Column("detail_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE draft_events SET detail_checked_at = now()
        WHERE player_id IN (
            SELECT DISTINCT player_id FROM draft_events
            WHERE deck_cards IS NOT NULL OR match_results IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.drop_column("draft_events", "detail_checked_at")
