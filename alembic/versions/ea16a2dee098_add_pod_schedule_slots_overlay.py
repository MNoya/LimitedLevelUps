"""Add pod_schedule_slots overlay and pod_format_votes

Revision ID: ea16a2dee098
Revises: l1f3t1m3st4ts
Create Date: 2026-08-29 12:02:17.332476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ea16a2dee098'
down_revision: Union[str, None] = 'l1f3t1m3st4ts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pod_schedule_slots',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('slot', sa.String(), nullable=False),
        sa.Column('formats', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('source', sa.String(), server_default='auto', nullable=False),
        sa.Column('decided_by', sa.String(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('day', 'slot', name='uq_pod_schedule_slot_day_slot'),
    )
    op.create_table(
        'pod_format_votes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('player_id', sa.String(), nullable=False),
        sa.Column('season_set_code', sa.String(), nullable=False),
        sa.Column('format_code', sa.String(), nullable=False),
        sa.Column('voted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'season_set_code', 'format_code', name='uq_pod_format_vote'),
    )
    op.create_index('ix_pod_format_votes_season', 'pod_format_votes', ['season_set_code'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pod_format_votes_season', table_name='pod_format_votes')
    op.drop_table('pod_format_votes')
    op.drop_table('pod_schedule_slots')
