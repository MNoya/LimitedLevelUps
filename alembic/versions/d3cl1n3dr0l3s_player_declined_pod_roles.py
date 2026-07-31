"""Add players.declined_pod_roles so a ping role switched off in /roles stays off

Revision ID: d3cl1n3dr0l3s
Revises: r3m0v3t1m3g8
Create Date: 2026-07-31 09:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "d3cl1n3dr0l3s"
down_revision: Union[str, None] = "r3m0v3t1m3g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column(
            "declined_pod_roles",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("players", "declined_pod_roles")
