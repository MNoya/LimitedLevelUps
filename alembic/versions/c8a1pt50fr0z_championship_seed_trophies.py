"""Add pod_championship_seeds.trophies so a frozen seed carries its trophy count with its rank and score

Revision ID: c8a1pt50fr0z
Revises: e4p0dc4rd1d5
Create Date: 2026-08-01 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8a1pt50fr0z"
down_revision: Union[str, None] = "e4p0dc4rd1d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pod_championship_seeds", sa.Column("trophies", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("pod_championship_seeds", "trophies")
