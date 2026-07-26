"""public_color_events: colour buckets resolved in SQL so a colours board reads one filtered slice

The colours leaderboard used to page every event on a board and bucket them in the browser, because
the bucket is not a column: 17lands encodes splashes by case (``WBg`` = WB main, green splash), and
the soup rule counts distinct colours with a stricter threshold on cube. That is fine for a board of
a few hundred events and unusable at ten thousand (SOS alone is 10.5k, the Arena Cube board 9k).

This view derives ``main_colors`` and ``is_multi`` once, for regular and cube boards alike, keyed by
the same ``set_code`` the frontend already asks for. A named chip then filters to one bucket
(``main_colors=eq.UR``, the largest on Arena Cube being 821 events) instead of downloading the board.

``public_colors_summary`` is rebuilt on top of it so the chip counts and the board behind a chip can
never disagree — they now read the same classification instead of two copies of the rule.

Revision ID: d3c8f1b6e4a7
Revises: c7b1e9d4a2f6
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d3c8f1b6e4a7"
down_revision: Union[str, None] = "c7b1e9d4a2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOUP_MIN_COLORS = 4
CUBE_SOUP_MIN_MAIN_COLORS = 3


_COLOR_EVENTS_SQL = f"""
    CREATE OR REPLACE VIEW public_color_events AS
    WITH src AS (
        SELECT
            set_code,
            slug,
            format,
            wins,
            losses,
            is_trophy,
            finished_at,
            COALESCE(colors, '') AS colors,
            (set_code = 'CUBE') AS is_cube,
            NULL::text AS display_name,
            NULL::text AS avatar_url
        FROM public_player_draft_events
        UNION ALL
        SELECT
            set_code,
            slug,
            format,
            wins,
            losses,
            is_trophy,
            finished_at,
            COALESCE(colors, '') AS colors,
            true AS is_cube,
            display_name,
            avatar_url
        FROM public_cube_season_events
    ),
    classified AS (
        SELECT
            s.*,
            (CASE WHEN x.main LIKE '%W%' THEN 'W' ELSE '' END) ||
            (CASE WHEN x.main LIKE '%U%' THEN 'U' ELSE '' END) ||
            (CASE WHEN x.main LIKE '%B%' THEN 'B' ELSE '' END) ||
            (CASE WHEN x.main LIKE '%R%' THEN 'R' ELSE '' END) ||
            (CASE WHEN x.main LIKE '%G%' THEN 'G' ELSE '' END) AS main_colors,
            (CASE WHEN x.all_colors LIKE '%W%' THEN 1 ELSE 0 END) +
            (CASE WHEN x.all_colors LIKE '%U%' THEN 1 ELSE 0 END) +
            (CASE WHEN x.all_colors LIKE '%B%' THEN 1 ELSE 0 END) +
            (CASE WHEN x.all_colors LIKE '%R%' THEN 1 ELSE 0 END) +
            (CASE WHEN x.all_colors LIKE '%G%' THEN 1 ELSE 0 END) AS effective_color_count
        FROM src s,
        LATERAL (SELECT regexp_replace(s.colors, '[a-z]', '', 'g') AS main, upper(s.colors) AS all_colors) x
    )
    SELECT
        set_code,
        slug,
        format,
        wins,
        losses,
        is_trophy,
        finished_at,
        display_name,
        avatar_url,
        main_colors,
        (
            effective_color_count >= {SOUP_MIN_COLORS}
            AND (NOT is_cube OR length(main_colors) >= {CUBE_SOUP_MIN_MAIN_COLORS})
        ) AS is_multi
    FROM classified;
"""


_COLORS_SUMMARY_SQL = """
    CREATE MATERIALIZED VIEW public_colors_summary AS
    WITH tagged AS (
        SELECT set_code, slug, is_trophy, main_colors AS colors
        FROM public_color_events
        WHERE main_colors <> ''
        UNION ALL
        SELECT set_code, slug, is_trophy, 'MULTI' AS colors
        FROM public_color_events
        WHERE is_multi
    )
    SELECT
        set_code,
        colors,
        SUM(CASE WHEN is_trophy THEN 1 ELSE 0 END)::int AS trophies,
        COUNT(*)::int AS events,
        COUNT(DISTINCT slug)::int AS players
    FROM tagged
    GROUP BY set_code, colors;
"""


_OLD_COLORS_SUMMARY_SQL = """
    CREATE MATERIALIZED VIEW public_colors_summary AS
    WITH events AS (
        SELECT set_code, slug, COALESCE(colors, '') AS colors, is_trophy, (set_code = 'CUBE') AS is_cube
        FROM public_player_draft_events
        UNION ALL
        SELECT set_code, slug, COALESCE(colors, '') AS colors, is_trophy, true AS is_cube
        FROM public_cube_season_events
    ),
    classified AS (
        SELECT
            e.set_code,
            e.slug,
            e.is_trophy,
            e.is_cube,
            (CASE WHEN x.main LIKE '%W%' THEN 'W' ELSE '' END) ||
            (CASE WHEN x.main LIKE '%U%' THEN 'U' ELSE '' END) ||
            (CASE WHEN x.main LIKE '%B%' THEN 'B' ELSE '' END) ||
            (CASE WHEN x.main LIKE '%R%' THEN 'R' ELSE '' END) ||
            (CASE WHEN x.main LIKE '%G%' THEN 'G' ELSE '' END) AS main_colors,
            (CASE WHEN x.all_colors LIKE '%W%' THEN 1 ELSE 0 END) +
            (CASE WHEN x.all_colors LIKE '%U%' THEN 1 ELSE 0 END) +
            (CASE WHEN x.all_colors LIKE '%B%' THEN 1 ELSE 0 END) +
            (CASE WHEN x.all_colors LIKE '%R%' THEN 1 ELSE 0 END) +
            (CASE WHEN x.all_colors LIKE '%G%' THEN 1 ELSE 0 END) AS effective_color_count
        FROM events e,
        LATERAL (SELECT regexp_replace(e.colors, '[a-z]', '', 'g') AS main, upper(e.colors) AS all_colors) x
    ),
    tagged AS (
        SELECT set_code, slug, is_trophy, main_colors AS colors
        FROM classified
        WHERE main_colors <> ''
        UNION ALL
        SELECT set_code, slug, is_trophy, 'MULTI' AS colors
        FROM classified
        WHERE effective_color_count >= 4 AND (NOT is_cube OR length(main_colors) >= 3)
    )
    SELECT
        set_code,
        colors,
        SUM(CASE WHEN is_trophy THEN 1 ELSE 0 END)::int AS trophies,
        COUNT(*)::int AS events,
        COUNT(DISTINCT slug)::int AS players
    FROM tagged
    GROUP BY set_code, colors;
"""


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS public_colors_summary;")
    op.execute(_COLOR_EVENTS_SQL)
    _grant("public_color_events")
    _create_colors_summary(_COLORS_SUMMARY_SQL)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS public_colors_summary;")
    op.execute("DROP VIEW IF EXISTS public_color_events;")
    _create_colors_summary(_OLD_COLORS_SUMMARY_SQL)


def _create_colors_summary(sql: str) -> None:
    op.execute(sql)
    op.execute("CREATE UNIQUE INDEX public_colors_summary_pk ON public_colors_summary (set_code, colors);")
    _grant("public_colors_summary")


def _grant(relation: str) -> None:
    for role in ("anon", "authenticated"):
        op.execute(f"""
            DO $$
            BEGIN
                IF to_regclass('public.{relation}') IS NOT NULL THEN
                    EXECUTE format('GRANT SELECT ON public.%s TO {role}', '{relation}');
                END IF;
            END
            $$;
        """)
