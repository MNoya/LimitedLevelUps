"""Grant authenticated role CRUD on the tracker tables

Revision ID: tr4ck3rgr4nt
Revises: tr4ck3r0001
Create Date: 2026-08-21

RLS policies were in place but the authenticated role lacked table-level
privileges. PostgREST checks GRANTs before RLS, so every logged-in read and
write to the tracker tables hit "permission denied".
"""
from typing import Sequence, Union

from alembic import op


revision: str = "tr4ck3rgr4nt"
down_revision: Union[str, None] = "tr4ck3r0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("tracker_draft_notes", "tracker_match_notes", "tracker_collection", "tracker_set_economy")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO authenticated;")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM authenticated;")
