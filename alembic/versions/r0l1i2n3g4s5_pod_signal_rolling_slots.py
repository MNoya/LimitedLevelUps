"""Key pod_signals uniqueness on (message_id, bucket, signal_date)

A rolled launcher column pre-creates the next day's slot on the message that is already posted, so one
launcher message can carry two rows of the same bucket.

Revision ID: r0l1i2n3g4s5
Revises: f0c1d2e3a4b5
Create Date: 2026-07-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "r0l1i2n3g4s5"
down_revision: Union[str, None] = "f0c1d2e3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE pod_signals DROP CONSTRAINT IF EXISTS uq_pod_signal_message_bucket")
    op.create_unique_constraint(
        "uq_pod_signal_message_bucket_date", "pod_signals", ["message_id", "bucket", "signal_date"],
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pod_signals DROP CONSTRAINT IF EXISTS uq_pod_signal_message_bucket_date")
    op.create_unique_constraint(
        "uq_pod_signal_message_bucket", "pod_signals", ["message_id", "bucket"],
    )
