"""Early Access drafts and pods score no points

Early Access drafts leave public_color_events, pods played before release leave public_pod_scoring, and
public_sets reads the board claim from draft_events

Revision ID: e4rlyacc3ss1
Revises: wk3ndr0l3s01
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e4rlyacc3ss1"
down_revision: Union[str, None] = "wk3ndr0l3s01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLOR_EVENTS_VIEW = """
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
        FROM public_player_draft_events e
        WHERE NOT EXISTS (
            SELECT 1 FROM sets s
            WHERE s.code = e.set_code
              AND e.format <> 'PodDraft'
              AND s.end_date IS NOT NULL
              AND e.started_at < ((s.start_date + time '12:00') AT TIME ZONE 'America/New_York')
        )
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
            effective_color_count >= 4
            AND (NOT is_cube OR length(main_colors) >= 3)
        ) AS is_multi
    FROM classified;
"""

OLD_COLOR_EVENTS_VIEW = """
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
            effective_color_count >= 4
            AND (NOT is_cube OR length(main_colors) >= 3)
        ) AS is_multi
    FROM classified;
"""

SETS_VIEW = """
    CREATE OR REPLACE VIEW public_sets AS
    WITH flagged AS (
        SELECT
            s.*,
            now() >= ((s.start_date + time '12:00') AT TIME ZONE 'America/New_York') AS released,
            (
                EXISTS (SELECT 1 FROM draft_events de WHERE de.set_id = s.id)
                OR EXISTS (SELECT 1 FROM self_reported_events se WHERE upper(se.set_code) = s.code)
            ) AS has_results
        FROM sets s
    ),
    next_up AS (
        SELECT code, has_results
        FROM flagged
        WHERE end_date IS NOT NULL AND NOT released
        ORDER BY start_date
        LIMIT 1
    ),
    board AS (
        SELECT COALESCE(
            (SELECT code FROM next_up WHERE has_results),
            (
                SELECT code FROM flagged
                WHERE end_date IS NOT NULL
                  AND released
                  AND now() < (((end_date + 1) + time '12:00') AT TIME ZONE 'America/New_York')
                ORDER BY start_date DESC
                LIMIT 1
            )
        ) AS code
    )
    SELECT
        f.code,
        f.name,
        f.start_date,
        f.end_date,
        (f.code = (SELECT code FROM board)) AS is_active,
        (NOT f.released) AS early,
        f.last_refreshed_at
    FROM flagged f
    WHERE f.start_date <= CURRENT_DATE OR f.has_results;
"""

OLD_SETS_VIEW = """
    CREATE OR REPLACE VIEW public_sets AS
    WITH flagged AS (
        SELECT
            s.*,
            now() >= ((s.start_date + time '12:00') AT TIME ZONE 'America/New_York') AS released,
            (
                EXISTS (SELECT 1 FROM player_stats ps WHERE ps.set_id = s.id)
                OR EXISTS (SELECT 1 FROM self_reported_events se WHERE upper(se.set_code) = s.code)
            ) AS has_results
        FROM sets s
    ),
    next_up AS (
        SELECT code, has_results
        FROM flagged
        WHERE end_date IS NOT NULL AND NOT released
        ORDER BY start_date
        LIMIT 1
    ),
    board AS (
        SELECT COALESCE(
            (SELECT code FROM next_up WHERE has_results),
            (
                SELECT code FROM flagged
                WHERE end_date IS NOT NULL
                  AND released
                  AND now() < (((end_date + 1) + time '12:00') AT TIME ZONE 'America/New_York')
                ORDER BY start_date DESC
                LIMIT 1
            )
        ) AS code
    )
    SELECT
        f.code,
        f.name,
        f.start_date,
        f.end_date,
        (f.code = (SELECT code FROM board)) AS is_active,
        (NOT f.released) AS early,
        f.last_refreshed_at
    FROM flagged f
    WHERE f.start_date <= CURRENT_DATE OR f.has_results;
"""

POD_SCORING_VIEW = """
    CREATE OR REPLACE VIEW public_pod_scoring AS
    SELECT
        p.slug,
        p.display_name,
        CASE WHEN p.avatar_hash IS NOT NULL AND p.discord_id IS NOT NULL
            THEN 'https://cdn.discordapp.com/avatars/' || p.discord_id || '/' || p.avatar_hash || '.png?size=128'
            ELSE NULL
        END AS avatar_url,
        pde.set_code,
        COUNT(*) FILTER (
            WHERE COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int >= 3
        )::int AS trophies,
        COUNT(*) FILTER (
            WHERE COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int = 2
        )::int AS two_win_finishes,
        COUNT(*) FILTER (
            WHERE COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int = 1
        )::int AS one_win_finishes,
        COUNT(*)::int AS events,
        COALESCE(
            SUM(COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int), 0
        )::int AS wins,
        COALESCE(
            SUM(COALESCE(NULLIF(split_part(pdp.record, '-', 2), ''), '0')::int), 0
        )::int AS losses,
        p.leaderboard_opt_in
    FROM pod_draft_participants pdp
    JOIN pod_draft_events pde ON pde.id = pdp.event_id
    JOIN players p ON p.id = pdp.player_id
    WHERE p.active = true
      AND pdp.record IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM sets s
          WHERE s.code = upper(pde.set_code)
            AND s.end_date IS NOT NULL
            AND pde.event_time < ((s.start_date + time '12:00') AT TIME ZONE 'America/New_York')
      )
    GROUP BY p.slug, p.display_name, p.avatar_hash, p.discord_id, pde.set_code, p.leaderboard_opt_in;
"""

OLD_POD_SCORING_VIEW = """
    CREATE OR REPLACE VIEW public_pod_scoring AS
    SELECT
        p.slug,
        p.display_name,
        CASE WHEN p.avatar_hash IS NOT NULL AND p.discord_id IS NOT NULL
            THEN 'https://cdn.discordapp.com/avatars/' || p.discord_id || '/' || p.avatar_hash || '.png?size=128'
            ELSE NULL
        END AS avatar_url,
        pde.set_code,
        COUNT(*) FILTER (
            WHERE COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int >= 3
        )::int AS trophies,
        COUNT(*) FILTER (
            WHERE COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int = 2
        )::int AS two_win_finishes,
        COUNT(*) FILTER (
            WHERE COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int = 1
        )::int AS one_win_finishes,
        COUNT(*)::int AS events,
        COALESCE(
            SUM(COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int), 0
        )::int AS wins,
        COALESCE(
            SUM(COALESCE(NULLIF(split_part(pdp.record, '-', 2), ''), '0')::int), 0
        )::int AS losses,
        p.leaderboard_opt_in
    FROM pod_draft_participants pdp
    JOIN pod_draft_events pde ON pde.id = pdp.event_id
    JOIN players p ON p.id = pdp.player_id
    WHERE p.active = true
      AND pdp.record IS NOT NULL
    GROUP BY p.slug, p.display_name, p.avatar_hash, p.discord_id, pde.set_code, p.leaderboard_opt_in;
"""


def upgrade() -> None:
    op.execute(COLOR_EVENTS_VIEW)
    op.execute(SETS_VIEW)
    op.execute(POD_SCORING_VIEW)
    op.execute("REFRESH MATERIALIZED VIEW public_colors_summary;")


def downgrade() -> None:
    op.execute(OLD_COLOR_EVENTS_VIEW)
    op.execute(OLD_SETS_VIEW)
    op.execute(OLD_POD_SCORING_VIEW)
    op.execute("REFRESH MATERIALIZED VIEW public_colors_summary;")
