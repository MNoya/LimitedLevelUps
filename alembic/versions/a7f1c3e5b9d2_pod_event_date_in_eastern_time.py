"""Move pod_draft_events.event_date onto the Eastern calendar day

Late Pods start at 8 PM ET, which is already the next UTC day, and the creation path took the UTC
date. Every Late Pod was filed a day ahead of the day in its own name, and one played on the last
night of a set landed in the next set's pod season.

Revision ID: a7f1c3e5b9d2
Revises: c3e5a7b9d1f4
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a7f1c3e5b9d2"
down_revision: Union[str, None] = "c3e5a7b9d1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE pod_draft_events
        SET event_date = (event_time AT TIME ZONE 'America/New_York')::date
        WHERE event_date <> (event_time AT TIME ZONE 'America/New_York')::date
    """)


def downgrade() -> None:
    pass
