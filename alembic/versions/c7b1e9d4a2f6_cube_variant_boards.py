"""Cube variant boards: one board per Arena cube, seasons for the powered cube only

Arena swaps the cube itself every few sets and 17lands files each under its own expansion
("Cube" for the original Arena Cube, "Cube - Powered", "Cube - Planar"). Ingest used to collapse
them all to the CUBE code, which made the variants indistinguishable; they now keep the raw 17lands
expansion, so this backfills the rows already stored under "CUBE" and reshapes the cube views.

Each variant gets a flat board at ``CUBE-<SLUG>``, where the slug comes from the expansion
("Cube - Planar" -> PLANAR, bare "Cube" -> ARENA), so a cube Arena introduces later surfaces as a
board with no migration. Only the powered cube also splits into per-set season boards
(``CUBE-<SET>``) — it recurs every few sets and is the family's flagship. Names and glyphs for the
slugs live in ``cube_variants.json``, read by both the bot and the site.

  public_cube_seasons          — one row per board, seasons and variants, discriminated by ``kind``
  public_cube_season_breakdown — per-(board, player, format) aggregates
  public_cube_season_events    — per-event rows, one per board an event belongs to

Revision ID: c7b1e9d4a2f6
Revises: r0l1i2n3g4s5
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7b1e9d4a2f6"
down_revision: Union[str, None] = "r0l1i2n3g4s5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEASONED_VARIANT = "POWERED"
LEGACY_VARIANT = "ARENA"
POWERED_EXPANSION = "Cube - Powered"
BURST_GAP_DAYS = 7


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


_BINNED_CTE = f"""\
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
              OR started_at - LAG(started_at) OVER w > INTERVAL '{BURST_GAP_DAYS} days'
            THEN 1 ELSE 0
        END AS new_burst
    FROM cube_events ce
    WHERE ce.variant = '{SEASONED_VARIANT}'
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
    op.execute(f"UPDATE draft_events SET expansion = '{POWERED_EXPANSION}' WHERE expansion = 'CUBE'")
    _create_views()


def downgrade() -> None:
    op.execute(f"UPDATE draft_events SET expansion = 'CUBE' WHERE expansion = '{POWERED_EXPANSION}'")
    for view in ("public_cube_season_events", "public_cube_season_breakdown", "public_cube_seasons"):
        op.execute(f"DROP VIEW IF EXISTS {view} CASCADE;")


def _create_views() -> None:
    op.execute("DROP VIEW IF EXISTS public_cube_seasons;")
    op.execute(f"""
        CREATE VIEW public_cube_seasons AS
        WITH {_BINNED_CTE}
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

    op.execute(f"""
        CREATE OR REPLACE VIEW public_cube_season_breakdown AS
        WITH {_BINNED_CTE}
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
        WITH {_BINNED_CTE}
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
        _grant_if_exists(view, "GRANT SELECT ON public.%s TO anon;")
        _grant_if_exists(view, "GRANT SELECT ON public.%s TO authenticated;")


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
