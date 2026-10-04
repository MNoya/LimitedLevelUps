"""Drop the retired Weekend pod role keys from players.declined_pod_roles

Revision ID: wk3ndr0l3s01
Revises: dt1ch3ck3d01
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op


revision: str = "wk3ndr0l3s01"
down_revision: Union[str, None] = "dt1ch3ck3d01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE players
        SET declined_pod_roles = array_remove(array_remove(declined_pod_roles, 'wknd_early'), 'wknd_late')
        WHERE declined_pod_roles && ARRAY['wknd_early', 'wknd_late']::varchar[]
        """
    )


def downgrade() -> None:
    pass
