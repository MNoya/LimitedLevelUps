"""Add section/subsection counts to public_episode_transcripts

Revision ID: tr4nscounts01
Revises: p0dcrd4uth01
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op


revision: str = "tr4nscounts01"
down_revision: Union[str, None] = "p0dcrd4uth01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW public_episode_transcripts AS
        SELECT
            youtube_id,
            segments,
            word_count,
            source,
            generated_at,
            (
                SELECT count(*) FROM jsonb_array_elements(segments) seg
                WHERE seg->>'heading' IS NOT NULL
            ) AS sections,
            (
                SELECT count(*) FROM jsonb_array_elements(segments) seg
                WHERE seg->>'subheading' IS NOT NULL
            ) AS subsections
        FROM episode_transcripts;
    """)
    _grant_if_exists("public_episode_transcripts", "GRANT SELECT ON public.%s TO anon;")
    _grant_if_exists("public_episode_transcripts", "GRANT SELECT ON public.%s TO authenticated;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_episode_transcripts;")
    op.execute("""
        CREATE VIEW public_episode_transcripts AS
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
