"""Fantasy pick-window checks run as their owner

Revision ID: f4n7w1nd0w5d
Revises: f4n7a5y1w0c1
Create Date: 2026-10-12
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f4n7w1nd0w5d"
down_revision: Union[str, None] = "f4n7a5y1w0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WINDOW_FUNCTIONS = (
    "fantasy_pick_window_open(text, int, timestamptz)",
    "fantasy_bracket_window_open(text, timestamptz)",
)


def upgrade() -> None:
    for function in WINDOW_FUNCTIONS:
        op.execute(f"ALTER FUNCTION {function} SECURITY DEFINER SET search_path = public")


def downgrade() -> None:
    for function in WINDOW_FUNCTIONS:
        op.execute(f"ALTER FUNCTION {function} SECURITY INVOKER RESET search_path")
