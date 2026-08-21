"""Personal draft tracker: annotation tables, per-draft 17lands detail, owner-scoped accounts view

Revision ID: tr4ck3r0001
Revises: n3wdr4ft3r01
Create Date: 2026-08-16

Four RLS-protected tables the frontend writes directly through PostgREST, all scoped by
auth.uid(). Notes key on the event_id emitted by public_player_draft_events, which unions
17lands and pod rows, so they carry no foreign key.

draft_events gains the objective per-draft detail fetched once from 17lands, since a finished
draft never changes: the pool's rare and mythic counts, the decklist split into maindeck and
sideboard, and the match results.

public_my_player_accounts matches the caller's Discord id out of the JWT, so a player only ever
sees their own Arena accounts; those names are public nowhere else on the site.

Guarded so a database without a Supabase auth schema still builds.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "tr4ck3r0001"
down_revision: Union[str, None] = "w1ldc4rd0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TRACKER_TABLES = (
    "tracker_draft_notes",
    "tracker_match_notes",
    "tracker_collection",
    "tracker_set_economy",
)

_POD_SLUG_SQL = "trim(both '-' from regexp_replace(lower(pde.name), '[^a-z0-9]+', '-', 'g'))"


def _events_view_sql(extra_17l: str, extra_pod: str) -> str:
    return f"""
        CREATE OR REPLACE VIEW public_player_draft_events AS
        SELECT
            p.slug,
            s.code AS set_code,
            de.id AS event_id,
            de.format,
            de.expansion,
            de.wins,
            de.losses,
            de.is_trophy,
            de.colors,
            de.started_at,
            de.finished_at,
            de.seventeenlands_event_id,
            CASE
                WHEN de.seventeenlands_event_id IS NOT NULL
                    THEN 'https://www.17lands.com/deck/' || de.seventeenlands_event_id
                ELSE NULL
            END AS external_url,
            NULL::text AS event_name,
            NULL::text AS pod_event_slug,
            de.end_rank{extra_17l}
        FROM draft_events de
        JOIN players p ON p.id = de.player_id
        JOIN sets s ON s.id = de.set_id
        WHERE p.active = true

        UNION ALL

        SELECT
            p.slug,
            pde.set_code,
            pdp.id AS event_id,
            'PodDraft' AS format,
            pde.set_code AS expansion,
            COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int AS wins,
            COALESCE(NULLIF(split_part(pdp.record, '-', 2), ''), '0')::int AS losses,
            COALESCE(NULLIF(split_part(pdp.record, '-', 1), ''), '0')::int >= 3 AS is_trophy,
            COALESCE(pdp.deck_colors, '') AS colors,
            pde.event_time AS started_at,
            pde.event_time AS finished_at,
            NULL::text AS seventeenlands_event_id,
            NULL::text AS external_url,
            pde.name AS event_name,
            {_POD_SLUG_SQL} AS pod_event_slug,
            NULL::text AS end_rank{extra_pod}
        FROM pod_draft_participants pdp
        JOIN pod_draft_events pde ON pde.id = pdp.event_id
        JOIN players p ON p.id = pdp.player_id
        WHERE p.active = true
          AND (pdp.placement IS NOT NULL OR pdp.record IS NOT NULL);
    """


_VIEW_EXTRA_17L = (
    ",\n            de.account_id,\n            de.pool_rares,\n            de.pool_mythics"
    ",\n            de.deck_cards,\n            de.match_results"
)
_VIEW_EXTRA_POD = (
    ",\n            NULL::int AS account_id,\n            NULL::int AS pool_rares"
    ",\n            NULL::int AS pool_mythics,\n            NULL::jsonb AS deck_cards"
    ",\n            NULL::jsonb AS match_results"
)


def upgrade() -> None:
    op.add_column("draft_events", sa.Column("pool_rares", sa.Integer(), nullable=True))
    op.add_column("draft_events", sa.Column("pool_mythics", sa.Integer(), nullable=True))
    op.add_column("draft_events", sa.Column("deck_cards", postgresql.JSONB(), nullable=True))
    op.add_column("draft_events", sa.Column("match_results", postgresql.JSONB(), nullable=True))
    op.execute(_events_view_sql(_VIEW_EXTRA_17L, _VIEW_EXTRA_POD))

    op.execute("""
        DO $$
        DECLARE
            has_auth boolean;
            t text;
            user_ref text;
        BEGIN
            SELECT EXISTS(
                SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth'
            ) INTO has_auth;

            user_ref := CASE WHEN has_auth
                THEN 'uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE'
                ELSE 'uuid NOT NULL' END;

            IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public'
                           AND tablename = 'tracker_draft_notes') THEN
                EXECUTE format('
                    CREATE TABLE tracker_draft_notes (
                        user_id        %s,
                        draft_event_id text        NOT NULL,
                        note           text,
                        deck_label     text,
                        rares          smallint,
                        mythics        smallint,
                        updated_at     timestamptz NOT NULL DEFAULT now(),
                        PRIMARY KEY (user_id, draft_event_id)
                    )', user_ref);
            END IF;

            IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public'
                           AND tablename = 'tracker_match_notes') THEN
                EXECUTE format('
                    CREATE TABLE tracker_match_notes (
                        user_id         %s,
                        draft_event_id  text        NOT NULL,
                        match_number    smallint    NOT NULL,
                        result          text,
                        opponent_colors text,
                        note            text,
                        updated_at      timestamptz NOT NULL DEFAULT now(),
                        PRIMARY KEY (user_id, draft_event_id, match_number),
                        CONSTRAINT tracker_match_result_valid
                            CHECK (result IS NULL OR result IN (''W'', ''L''))
                    )', user_ref);
            END IF;

            IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public'
                           AND tablename = 'tracker_collection') THEN
                EXECUTE format('
                    CREATE TABLE tracker_collection (
                        user_id    %s,
                        set_code   text        NOT NULL,
                        card_name  text        NOT NULL,
                        owned      smallint    NOT NULL DEFAULT 0,
                        updated_at timestamptz NOT NULL DEFAULT now(),
                        PRIMARY KEY (user_id, set_code, card_name),
                        CONSTRAINT tracker_collection_owned_range
                            CHECK (owned BETWEEN 0 AND 4)
                    )', user_ref);
            END IF;

            IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public'
                           AND tablename = 'tracker_set_economy') THEN
                EXECUTE format('
                    CREATE TABLE tracker_set_economy (
                        user_id           %s,
                        set_code          text        NOT NULL,
                        packs_owned       smallint    NOT NULL DEFAULT 0,
                        golden_packs      smallint    NOT NULL DEFAULT 0,
                        mastery_level     smallint    NOT NULL DEFAULT 0,
                        ranked_season_packs smallint  NOT NULL DEFAULT 0,
                        updated_at        timestamptz NOT NULL DEFAULT now(),
                        PRIMARY KEY (user_id, set_code)
                    )', user_ref);
            END IF;

            FOREACH t IN ARRAY ARRAY['tracker_draft_notes', 'tracker_match_notes',
                                     'tracker_collection', 'tracker_set_economy'] LOOP
                EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
                IF has_auth THEN
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_select', t);
                    EXECUTE format('CREATE POLICY %I ON %I FOR SELECT USING (auth.uid() = user_id)',
                                   t || '_select', t);
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_insert', t);
                    EXECUTE format('CREATE POLICY %I ON %I FOR INSERT WITH CHECK (auth.uid() = user_id)',
                                   t || '_insert', t);
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_update', t);
                    EXECUTE format('CREATE POLICY %I ON %I FOR UPDATE USING (auth.uid() = user_id)
                                    WITH CHECK (auth.uid() = user_id)', t || '_update', t);
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_delete', t);
                    EXECUTE format('CREATE POLICY %I ON %I FOR DELETE USING (auth.uid() = user_id)',
                                   t || '_delete', t);
                END IF;
            END LOOP;

            IF EXISTS (
                SELECT 1 FROM pg_proc pr
                JOIN pg_namespace ns ON ns.oid = pr.pronamespace
                WHERE ns.nspname = 'auth' AND pr.proname = 'jwt'
            ) THEN
                EXECUTE $view$
                    CREATE OR REPLACE VIEW public_my_player_accounts AS
                    SELECT p.slug,
                           pa.id   AS account_id,
                           pa.name AS account_name,
                           count(de.id) AS events
                    FROM player_accounts pa
                    JOIN players p ON p.id = pa.player_id
                    LEFT JOIN draft_events de ON de.account_id = pa.id
                    WHERE p.discord_id = (auth.jwt() -> 'user_metadata' ->> 'provider_id')
                    GROUP BY p.slug, pa.id, pa.name
                $view$;
                GRANT SELECT ON public_my_player_accounts TO anon, authenticated;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_my_player_accounts;")
    for table in TRACKER_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table};")
    op.execute("DROP VIEW IF EXISTS public_player_draft_events;")
    op.execute(_events_view_sql("", ""))
    for column in ("match_results", "deck_cards", "pool_mythics", "pool_rares"):
        op.drop_column("draft_events", column)
