"""Episode transcripts table + public_episode_transcripts view

Revision ID: tr4nscr1pt5ep
Revises: ea16a2dee098
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "tr4nscr1pt5ep"
down_revision: Union[str, None] = "ea16a2dee098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "episode_transcripts",
        sa.Column("youtube_id", sa.String(), nullable=False),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.String(), server_default="whisper-large-v3", nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("youtube_id"),
    )

    op.execute("""
        CREATE OR REPLACE VIEW public_episode_transcripts AS
        SELECT
            youtube_id,
            segments,
            word_count,
            source,
            generated_at
        FROM episode_transcripts;
    """)

    _grant_if_exists("public_episode_transcripts", "GRANT SELECT ON public.%s TO anon;")
    _grant_if_exists("public_episode_transcripts", "GRANT SELECT ON public.%s TO authenticated;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_episode_transcripts;")
    op.drop_table("episode_transcripts")


def _grant_if_exists(view: str, statement: str) -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.{view}') IS NOT NULL THEN
                EXECUTE format('{statement}', '{view}');
            END IF;
        END
        $$;
    """)
