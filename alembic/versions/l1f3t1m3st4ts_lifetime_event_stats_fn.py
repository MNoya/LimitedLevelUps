"""Aggregate function for the lifetime profile's filtered record strip

Revision ID: l1f3t1m3st4ts
Revises: pl4y3rl1f3t1
Create Date: 2026-08-28

The lifetime event log paginates, so a format or colors filter matching more than one page can only
be summed exactly from the server. PostgREST aggregate functions are off, so this exposes one fixed
aggregate over public_player_draft_events, mirroring the log's filters, callable by the browser roles.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "l1f3t1m3st4ts"
down_revision: Union[str, None] = "pl4y3rl1f3t1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FUNCTION_SIGNATURE = "public.public_lifetime_event_stats(text, text[], text, text, date, date)"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.public_lifetime_event_stats(
            p_slug text,
            p_formats text[] DEFAULT NULL,
            p_format_like text DEFAULT NULL,
            p_color_pattern text DEFAULT NULL,
            p_start date DEFAULT NULL,
            p_end_exclusive date DEFAULT NULL
        )
        RETURNS TABLE(events bigint, wins bigint, losses bigint, trophies bigint)
        LANGUAGE plpgsql STABLE
        SET search_path = public
        AS $$
        BEGIN
            RETURN QUERY
            SELECT count(*)::bigint,
                   coalesce(sum(e.wins), 0)::bigint,
                   coalesce(sum(e.losses), 0)::bigint,
                   count(*) FILTER (WHERE e.is_trophy)::bigint
            FROM public_player_draft_events e
            WHERE e.slug = p_slug
              AND e.format NOT ILIKE 'MidWeek%'
              AND (p_formats IS NULL OR e.format = ANY(p_formats))
              AND (p_format_like IS NULL OR e.format ILIKE '%' || p_format_like || '%')
              AND (p_color_pattern IS NULL OR e.colors ~ p_color_pattern)
              AND (p_start IS NULL OR e.finished_at >= p_start)
              AND (p_end_exclusive IS NULL OR e.finished_at < p_end_exclusive);
        END;
        $$;
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION {FUNCTION_SIGNATURE} TO anon, authenticated")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION_SIGNATURE}")
