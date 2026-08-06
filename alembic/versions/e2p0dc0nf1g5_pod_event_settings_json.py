"""Hold pod Draftmancer setup on the event row

The Settings panel's pick timer, packs, cards per pack, pick mode, and max players were pushed straight
at the live Draftmancer socket and stored nowhere, so the controls could only appear once a session was
connected. A scheduled pod showed a panel missing five of its settings until someone launched the lobby.

A JSON blob rather than one column per value: these are free-form session parameters, nothing queries
them, and the next one to be added should cost a key in ``bot/services/pod_event_settings.py`` instead
of a migration.

Revision ID: e2p0dc0nf1g5
Revises: c8a1pt50fr0z
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "e2p0dc0nf1g5"
down_revision: Union[str, None] = "c8a1pt50fr0z"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pod_draft_events",
        sa.Column("settings", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("pod_draft_events", "settings")
