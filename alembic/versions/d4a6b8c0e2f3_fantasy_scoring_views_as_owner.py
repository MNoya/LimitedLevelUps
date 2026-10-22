"""Read the Fantasy scoring views as their owner so the public views work for site visitors

Revision ID: d4a6b8c0e2f3
Revises: c3f5a7e9b1d2
Create Date: 2026-10-22
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4a6b8c0e2f3"
down_revision: Union[str, None] = "c3f5a7e9b1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCORING_VIEWS = (
    "fantasy_effective_picks",
    "fantasy_slot_round_points",
    "fantasy_bracket_points",
    "fantasy_member_scores",
)
VIEW_STATEMENTS = tuple(f"ALTER VIEW {view} SET (security_invoker = false)" for view in SCORING_VIEWS)


def upgrade() -> None:
    for statement in VIEW_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for view in SCORING_VIEWS:
        op.execute(f"ALTER VIEW {view} SET (security_invoker = true)")
