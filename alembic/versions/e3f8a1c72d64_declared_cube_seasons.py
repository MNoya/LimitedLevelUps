"""Declare cube seasons as date ranges, and materialize the board list

A cube season was derived per read: sort every cube event, mark a >7-day gap as a new burst, then
give every event in a burst the season of the set live when the burst started. That is a lookbehind,
so no index applies and no set_code filter can push past it — asking for one board computed all of
them and discarded the rest. Three of those per leaderboard page load, on every page and not only
cube ones, was ~21 GB of temp-file writes against the Disk IO Budget.

The whole pipeline reconstructed five date ranges that WotC announces in advance. They are declared
in cube_variants.json now, seeded into this table, and the views join them as plain ranges. A run
with no declared season gets no season board; its drafts still count on the variant's own board.

public_cube_seasons also becomes a matview. It is eight rows, it counts distinct players across
every cube draft to build them, and the site fetches it on every leaderboard page to fill the set
picker, cube page or not. Its rows only move when cube drafts land, so the refresh tick owns it.

Revision ID: e3f8a1c72d64
Revises: c1b5e6f8a2cd
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f8a1c72d64"
down_revision: Union[str, None] = "c1b5e6f8a2cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_VARIANT = "ARENA"

_AVATAR_URL_SQL = """\
CASE WHEN b.avatar_hash IS NOT NULL AND b.discord_id IS NOT NULL
    THEN 'https://cdn.discordapp.com/avatars/' || b.discord_id || '/' || b.avatar_hash || '.png?size=128'
    ELSE NULL
END"""

_FORMAT_LABEL_CASE = """\
CASE
    WHEN b.format = 'PremierDraft' THEN 'Premier'
    WHEN b.format = 'TradDraft' THEN 'Trad'
    WHEN b.format IN (
        'Sealed',
        'TradSealed',
        'ArenaDirect_Sealed',
        'QualifierPlayInSealed',
        'QualifierPlayInTradSealed',
        'Qualifier_D1_Sealed',
        'Qualifier_D2_Sealed'
    ) THEN 'Sealed'
    WHEN b.format IN ('QuickDraft', 'PickTwoDraft', 'Emblem_QuickDraft') THEN 'Quick'
    WHEN b.format = 'LimitedChampionshipQualifier_Draft1' THEN 'LCQ Draft 1'
    WHEN b.format = 'LimitedChampionshipQualifier_Draft2' THEN 'LCQ Draft 2'
    ELSE NULL
END"""

_EVENT_COLUMNS = """\
    id,
    player_id,
    format,
    expansion,
    wins,
    losses,
    is_trophy,
    colors,
    end_rank,
    started_at,
    finished_at,
    seventeenlands_event_id,
    slug,
    display_name,
    avatar_hash,
    discord_id,
    kind,
    label,
    set_code"""

# One row per cube draft per board it belongs to: its variant board always, plus its season board
# when the run it was played in is declared.
#
# NOT MATERIALIZED matters as much as dropping the window functions did. Both arms read
# cube_events, and a CTE with two references is spooled to disk by default, which put 17k wide rows
# through work_mem before any filter applied. Inlined, PostgREST's set_code filter reaches each
# arm's scan and one board reads one board.
_BINNED_CTE = f"""\
cube_events AS NOT MATERIALIZED (
    SELECT
        de.id,
        de.player_id,
        de.format,
        de.expansion,
        de.wins,
        de.losses,
        de.is_trophy,
        de.colors,
        de.end_rank,
        de.started_at,
        de.finished_at,
        de.seventeenlands_event_id,
        p.slug,
        p.display_name,
        p.avatar_hash,
        p.discord_id,
        UPPER(COALESCE(NULLIF(split_part(de.expansion, ' - ', 2), ''), '{LEGACY_VARIANT}')) AS variant
    FROM draft_events de
    JOIN players p ON p.id = de.player_id
    JOIN sets s ON s.id = de.set_id
    WHERE s.code = 'CUBE' AND p.active = true AND de.started_at IS NOT NULL
),
season_rows AS (
    SELECT
        ce.*,
        'season'::text AS kind,
        cs.set_code AS label,
        'CUBE-' || cs.set_code AS set_code
    FROM cube_events ce
    JOIN cube_seasons cs
        ON cs.variant = ce.variant
       AND ce.started_at::date BETWEEN cs.start_date AND cs.end_date
),
variant_rows AS (
    SELECT
        ce.*,
        'variant'::text AS kind,
        ce.variant AS label,
        'CUBE-' || ce.variant AS set_code
    FROM cube_events ce
),
binned AS (
    SELECT
{_EVENT_COLUMNS}
    FROM season_rows
    UNION ALL
    SELECT
{_EVENT_COLUMNS}
    FROM variant_rows
)"""


# The burst-detection binning these views used before, restored verbatim on downgrade.
_LEGACY_BINNED_CTE = f"""\
cube_events AS (
    SELECT
        de.id,
        de.player_id,
        de.format,
        de.expansion,
        de.wins,
        de.losses,
        de.is_trophy,
        de.colors,
        de.end_rank,
        de.started_at,
        de.finished_at,
        de.seventeenlands_event_id,
        p.slug,
        p.display_name,
        p.avatar_hash,
        p.discord_id,
        UPPER(COALESCE(NULLIF(split_part(de.expansion, ' - ', 2), ''), '{LEGACY_VARIANT}')) AS variant
    FROM draft_events de
    JOIN players p ON p.id = de.player_id
    JOIN sets s ON s.id = de.set_id
    WHERE s.code = 'CUBE' AND p.active = true AND de.started_at IS NOT NULL
),
seasons AS (
    SELECT
        code,
        start_date,
        LEAD(start_date) OVER (ORDER BY start_date) AS next_start
    FROM sets
    WHERE code <> 'CUBE'
),
marked AS (
    SELECT
        ce.*,
        CASE
            WHEN LAG(started_at) OVER w IS NULL
              OR started_at - LAG(started_at) OVER w > INTERVAL '7 days'
            THEN 1 ELSE 0
        END AS new_burst
    FROM cube_events ce
    WHERE ce.variant = 'POWERED'
    WINDOW w AS (ORDER BY started_at)
),
bursts AS (
    SELECT
        m.*,
        SUM(new_burst) OVER (ORDER BY started_at ROWS UNBOUNDED PRECEDING) AS burst_id
    FROM marked m
),
anchored AS (
    SELECT
        br.*,
        MIN(started_at) OVER (PARTITION BY burst_id) AS burst_start
    FROM bursts br
),
season_rows AS (
    SELECT
        a.*,
        'season'::text AS kind,
        seasons.code AS label,
        'CUBE-' || seasons.code AS set_code
    FROM anchored a
    JOIN seasons
        ON a.burst_start::date >= seasons.start_date
       AND (seasons.next_start IS NULL OR a.burst_start::date < seasons.next_start)
),
variant_rows AS (
    SELECT
        ce.*,
        'variant'::text AS kind,
        ce.variant AS label,
        'CUBE-' || ce.variant AS set_code
    FROM cube_events ce
),
binned AS (
    SELECT
{_EVENT_COLUMNS}
    FROM season_rows
    UNION ALL
    SELECT
{_EVENT_COLUMNS}
    FROM variant_rows
)"""


def upgrade() -> None:
    op.create_table(
        "cube_seasons",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("variant", sa.String(), nullable=False),
        sa.Column("set_code", sa.String(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("variant", "set_code", name="uq_cube_season_per_variant"),
    )
    op.create_index("ix_cube_seasons_variant_dates", "cube_seasons",
                    ["variant", "start_date", "end_date"])
    # The cube filter sits on the joined sets row, so without this every cube read scanned the
    # whole event log to find the 18k rows it wanted
    op.create_index("ix_draft_events_set_id", "draft_events", ["set_id"])
    _create_views(_BINNED_CTE, materialize_board_list=True)


def downgrade() -> None:
    _create_views(_LEGACY_BINNED_CTE, materialize_board_list=False)
    op.drop_index("ix_draft_events_set_id", table_name="draft_events")
    op.drop_index("ix_cube_seasons_variant_dates", table_name="cube_seasons")
    op.drop_table("cube_seasons")


def _create_views(binned_cte: str, materialize_board_list: bool) -> None:
    """CREATE OR REPLACE for the two the colour views read: public_color_events and the
    public_colors_summary matview sit on public_cube_season_events, so a drop would need a CASCADE
    that takes them too. Output columns are unchanged, which is what makes the replace legal.
    public_cube_seasons has no dependents, so it can be dropped and swapped between kinds.
    """
    # IF EXISTS does not cover a name that exists as the other kind, and this migration swaps
    # public_cube_seasons between view and matview in both directions
    op.execute("""
        DO $$
        DECLARE kind "char";
        BEGIN
            SELECT relkind INTO kind FROM pg_class WHERE relname = 'public_cube_seasons';
            IF kind = 'm' THEN
                DROP MATERIALIZED VIEW public_cube_seasons;
            ELSIF kind = 'v' THEN
                DROP VIEW public_cube_seasons;
            END IF;
        END $$;
    """)
    op.execute(f"""
        CREATE {'MATERIALIZED VIEW' if materialize_board_list else 'VIEW'} public_cube_seasons AS
        WITH {binned_cte}
        SELECT
            b.set_code,
            b.kind,
            b.label,
            s.name AS name,
            COALESCE(s.start_date, MIN(b.started_at)::date) AS start_date,
            MIN(b.started_at)::date AS first_event,
            MAX(b.started_at)::date AS last_event,
            COUNT(*)::int AS events,
            COUNT(DISTINCT b.player_id)::int AS players
        FROM binned b
        LEFT JOIN sets s ON b.kind = 'season' AND s.code = b.label
        GROUP BY b.set_code, b.kind, b.label, s.name, s.start_date;
    """)
    if materialize_board_list:
        op.execute("CREATE UNIQUE INDEX uq_cube_seasons_board ON public_cube_seasons (set_code);")

    op.execute(f"""
        CREATE OR REPLACE VIEW public_cube_season_breakdown AS
        WITH {binned_cte}
        SELECT
            b.set_code,
            b.slug,
            b.display_name,
            {_AVATAR_URL_SQL} AS avatar_url,
            {_FORMAT_LABEL_CASE} AS format_label,
            COUNT(*)::int AS events,
            SUM(b.wins)::int AS wins,
            SUM(b.losses)::int AS losses,
            SUM(CASE WHEN b.is_trophy THEN 1 ELSE 0 END)::int AS trophies
        FROM binned b
        GROUP BY b.set_code, b.slug, b.display_name, {_AVATAR_URL_SQL}, {_FORMAT_LABEL_CASE}
        HAVING ({_FORMAT_LABEL_CASE}) IS NOT NULL;
    """)

    op.execute(f"""
        CREATE OR REPLACE VIEW public_cube_season_events AS
        WITH {binned_cte}
        SELECT
            b.slug,
            b.set_code,
            b.id AS event_id,
            b.format,
            b.expansion,
            b.wins,
            b.losses,
            b.is_trophy,
            b.colors,
            b.started_at,
            b.finished_at,
            b.seventeenlands_event_id,
            CASE
                WHEN b.seventeenlands_event_id IS NOT NULL
                    THEN 'https://www.17lands.com/deck/' || b.seventeenlands_event_id
                ELSE NULL
            END AS external_url,
            NULL::text AS event_name,
            NULL::text AS pod_event_slug,
            b.display_name,
            {_AVATAR_URL_SQL} AS avatar_url,
            b.end_rank
        FROM binned b;
    """)

    for view in ("public_cube_seasons", "public_cube_season_breakdown", "public_cube_season_events"):
        op.execute(f"GRANT SELECT ON public.{view} TO anon;")
        op.execute(f"GRANT SELECT ON public.{view} TO authenticated;")
