"""Track the round a pod participant dropped in

An organizer marks a player out of a running pod; the round they left in is recorded so every match
of theirs from that point forward is forfeited to a bye for the opponent.

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2d4f6a8c0e1"
down_revision: Union[str, None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pod_draft_participants", sa.Column("dropped_round", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("pod_draft_participants", "dropped_round")
