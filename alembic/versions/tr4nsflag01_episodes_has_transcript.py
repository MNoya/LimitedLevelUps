"""Add has_transcript to public_episodes so the client knows before the transcript loads

Revision ID: tr4nsflag01
Revises: c0b3ca7d5747
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op


revision: str = "tr4nsflag01"
down_revision: Union[str, None] = "c0b3ca7d5747"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BASE_COLUMNS = """
            id,
            guid,
            kind,
            number,
            title,
            link,
            summary,
            image,
            published_at,
            duration_seconds,
            audio_url,
            youtube_id,
            category,
            set_code,
            set_name,
            set_released_at
"""


def upgrade() -> None:
    op.execute(f"""
        CREATE OR REPLACE VIEW public_episodes AS
        SELECT
{_BASE_COLUMNS},
            youtube_id IS NOT NULL
                AND EXISTS (SELECT 1 FROM episode_transcripts t WHERE t.youtube_id = episodes.youtube_id)
                AS has_transcript
        FROM episodes
        ORDER BY published_at DESC;
    """)
    _grant_if_exists("public_episodes", "GRANT SELECT ON public.%s TO anon;")
    _grant_if_exists("public_episodes", "GRANT SELECT ON public.%s TO authenticated;")


def downgrade() -> None:
    op.execute(f"""
        CREATE OR REPLACE VIEW public_episodes AS
        SELECT
{_BASE_COLUMNS}
        FROM episodes
        ORDER BY published_at DESC;
    """)
    _grant_if_exists("public_episodes", "GRANT SELECT ON public.%s TO anon;")
    _grant_if_exists("public_episodes", "GRANT SELECT ON public.%s TO authenticated;")


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
