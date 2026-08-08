"""Record a pod signup confirming, and where its card sits

Two columns for the confirmation window. `confirmed_at` is separate from `rsvp` so every existing roster
reader keeps working unchanged, and the answers survive a redeploy inside the hour they are collected in.
`confirm_card_message_id` remembers the card the bot posted, since locating it by reading thread history
is an API call in front of a player's click and survives no restart.

Revision ID: c0nf1rm5eat
Revises: e2p0dc0nf1g5
Create Date: 2026-08-08 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c0nf1rm5eat"
down_revision: Union[str, None] = "e2p0dc0nf1g5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pod_signal_members", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("pod_signals", sa.Column("confirm_card_message_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("pod_signals", "confirm_card_message_id")
    op.drop_column("pod_signal_members", "confirmed_at")
