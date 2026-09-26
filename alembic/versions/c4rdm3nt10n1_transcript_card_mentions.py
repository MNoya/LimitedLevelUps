"""Transcript card mentions table + public_set_review_card_mentions view

Revision ID: c4rdm3nt10n1
Revises: a8b9c0d1e2f3
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4rdm3nt10n1"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SET_REVIEW_CARD_MENTIONS_VIEW = """
        CREATE OR REPLACE VIEW public_set_review_card_mentions AS
        SELECT DISTINCT ON (set_code, card_name)
            set_code,
            card_name,
            youtube_id,
            title,
            segment_index,
            t
        FROM (
            SELECT
                episode.set_code,
                mention.card_name,
                mention.youtube_id,
                episode.title,
                mention.segment_index,
                mention.t,
                mention.opens_subtopic,
                episode.published_at,
                count(*) OVER (PARTITION BY episode.set_code, mention.youtube_id, mention.card_name)
                    AS episode_mentions
            FROM transcript_card_mentions mention
            JOIN episodes episode ON episode.youtube_id = mention.youtube_id
            JOIN sets indexed_set ON indexed_set.code = episode.set_code
            WHERE episode.category = 'Set Review'
                AND episode.title NOT ILIKE '%first impression%'
                AND indexed_set.start_date >= DATE '2026-09-29'
        ) ranked
        ORDER BY set_code, card_name, opens_subtopic DESC, episode_mentions DESC, published_at DESC, t;
"""


def upgrade() -> None:
    op.create_table(
        "transcript_card_mentions",
        sa.Column("youtube_id", sa.String(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("card_name", sa.String(), nullable=False),
        sa.Column("t", sa.Integer(), nullable=False),
        sa.Column("opens_subtopic", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["youtube_id"], ["episode_transcripts.youtube_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("youtube_id", "segment_index", "card_name"),
    )

    op.execute("""
        INSERT INTO transcript_card_mentions (youtube_id, segment_index, card_name, t, opens_subtopic)
        SELECT DISTINCT
            transcript.youtube_id,
            segment.ordinality - 1,
            card->>'name',
            (segment.value->>'t')::int,
            NULLIF(segment.value->>'heading', '') IS NOT NULL OR NULLIF(segment.value->>'subheading', '') IS NOT NULL
        FROM episode_transcripts transcript
        CROSS JOIN LATERAL jsonb_array_elements(transcript.segments) WITH ORDINALITY AS segment(value, ordinality)
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(segment.value->'cards', '[]'::jsonb)) AS card;
    """)

    op.execute(SET_REVIEW_CARD_MENTIONS_VIEW)

    _grant_if_exists("public_set_review_card_mentions", "GRANT SELECT ON public.%s TO anon;")
    _grant_if_exists("public_set_review_card_mentions", "GRANT SELECT ON public.%s TO authenticated;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_set_review_card_mentions;")
    op.drop_table("transcript_card_mentions")


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
