"""Store a Set Championship's VOD and expose it with the event's Discord thread for the Hall of Fame

Revision ID: f6c8d0e2a4b6
Revises: e5b7c9d1f3a4
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6c8d0e2a4b6"
down_revision: Union[str, None] = "e5b7c9d1f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pod_draft_events", sa.Column("vod_url", sa.String(), nullable=True))
    op.execute("""
        CREATE VIEW public_pod_championships AS
        SELECT
            pde.id                AS event_id,
            pde.set_code,
            pde.discord_thread_id AS thread_id,
            pde.vod_url
        FROM pod_draft_events pde
        WHERE pde.name ILIKE '%championship%'
          AND pde.kind IS DISTINCT FROM 'mock';
    """)
    for role in ("anon", "authenticated"):
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'GRANT SELECT ON public.public_pod_championships TO {role}';
                END IF;
            END $$;
        """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_pod_championships")
    op.drop_column("pod_draft_events", "vod_url")
