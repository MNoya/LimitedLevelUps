"""Daily Sealed original deck basic lands

Revision ID: e5b2a7s1i3c9
Revises: d4i1y5e4l3d1
Create Date: 2026-11-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e5b2a7s1i3c9"
down_revision: Union[str, None] = "d4i1y5e4l3d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POOLS_VIEW_COLUMNS = """
       p.day,
       p.set_code,
       row_number() OVER (PARTITION BY p.set_code ORDER BY p.day)::int AS pool_number,
       p.format,
       p.cards,
       p.original_main,
       p.colors,
       p.wins,
       p.losses,
       (SELECT count(*) FROM daily_sealed_builds b WHERE b.day = p.day)::int AS build_count"""

POOLS_VIEW_SOURCE = """
FROM daily_sealed_pools p
WHERE p.day <= daily_sealed_today();
"""


def upgrade() -> None:
    op.add_column("daily_sealed_pools", sa.Column("original_basics", postgresql.JSONB(), nullable=True))
    op.execute(
        "CREATE OR REPLACE VIEW public_daily_sealed_pools AS SELECT"
        f"{POOLS_VIEW_COLUMNS},\n       p.original_basics{POOLS_VIEW_SOURCE}"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_daily_sealed_pools;")
    op.execute(f"CREATE VIEW public_daily_sealed_pools AS SELECT{POOLS_VIEW_COLUMNS}{POOLS_VIEW_SOURCE}")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                GRANT SELECT ON public_daily_sealed_pools TO anon;
                GRANT SELECT ON public_daily_sealed_pools TO authenticated;
            END IF;
        END $$;
    """)
    op.drop_column("daily_sealed_pools", "original_basics")
