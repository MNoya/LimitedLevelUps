"""Add pod_draft_events card_channel_id / card_message_id so a signal-less pod owns a channel card

Revision ID: e4p0dc4rd1d5
Revises: d3cl1n3dr0l3s
Create Date: 2026-07-31 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e4p0dc4rd1d5"
down_revision: Union[str, None] = "d3cl1n3dr0l3s"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pod_draft_events", sa.Column("card_channel_id", sa.String(), nullable=True))
    op.add_column("pod_draft_events", sa.Column("card_message_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("pod_draft_events", "card_message_id")
    op.drop_column("pod_draft_events", "card_channel_id")
