"""Mark the pod-standings wildcard on a Set Championship seed

Adds pod_championship_seeds.wildcard so the seat cut can reserve a place for the
best pod-season player who did not qualify on the leaderboard.

Revision ID: w1ldc4rd0001
Revises: n3wdr4ft3r01
Create Date: 2026-08-20 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "w1ldc4rd0001"
down_revision: Union[str, None] = "n3wdr4ft3r01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pod_championship_seeds",
        sa.Column("wildcard", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("pod_championship_seeds", "wildcard")
