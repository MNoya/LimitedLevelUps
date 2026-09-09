"""Grant authenticated SELECT on the pod card stats views

Revision ID: p0dcrd4uth01
Revises: tr4nsflag01
Create Date: 2026-09-09

public_pod_card_stats and public_pod_archetype_stats shipped with a grant to
anon only, so /pods/<board>/data 403s for logged-in visitors, who read as the
authenticated role.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "p0dcrd4uth01"
down_revision: Union[str, None] = "tr4nsflag01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VIEWS = ["public_pod_card_stats", "public_pod_archetype_stats"]


def upgrade() -> None:
    for view in _VIEWS:
        _grant_if_exists(view, "GRANT SELECT ON public.%s TO authenticated;")


def downgrade() -> None:
    for view in _VIEWS:
        _grant_if_exists(view, "REVOKE SELECT ON public.%s FROM authenticated;")


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
