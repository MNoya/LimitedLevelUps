"""Fantasy Worlds tables, scoring views and public views

Revision ID: f4n7a5y1w0c1
Revises: e4rlyacc3ss1
Create Date: 2026-10-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4n7a5y1w0c1"
down_revision: Union[str, None] = "e4rlyacc3ss1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PUBLIC_VIEWS = (
    "public_fantasy_players",
    "public_fantasy_results",
    "public_fantasy_standings",
    "public_fantasy_lineups",
    "public_fantasy_bracket_picks",
    "public_fantasy_event_state",
)
INTERNAL_VIEWS = (
    "fantasy_effective_picks",
    "fantasy_slot_round_points",
    "fantasy_bracket_points",
    "fantasy_member_scores",
)
MEMBER_TABLES = ("fantasy_picks", "fantasy_bracket_picks")
PRIVATE_TABLES = ("fantasy_events", "fantasy_players", "fantasy_results", "fantasy_rounds", "fantasy_members")

VIEWER_IS_MEMBER = "(m.user_id::text = (nullif(current_setting('request.jwt.claims', true), '')::json->>'sub'))"
MEMBER_KEY = "left(encode(sha256(m.user_id::text::bytea), 'hex'), 16)"

EFFECTIVE_PICKS_SQL = """
CREATE OR REPLACE VIEW fantasy_effective_picks WITH (security_invoker = true) AS
WITH candidate AS (
    SELECT p.user_id, p.event_code, p.slot, p.from_round, p.player_id, p.updated_at, e.cut_round,
           lag(p.player_id) OVER slot_rows AS replaced_player_id,
           row_number() OVER slot_rows AS pick_order
    FROM fantasy_picks p
    JOIN fantasy_events e ON e.code = p.event_code
    WINDOW slot_rows AS (PARTITION BY p.user_id, p.event_code, p.slot ORDER BY p.from_round)
), valid AS (
    SELECT c.*
    FROM candidate c
    WHERE (c.pick_order = 1 AND c.from_round = 1)
       OR (c.pick_order = 2 AND c.from_round = c.cut_round + 1 AND NOT EXISTS (
               SELECT 1 FROM fantasy_results r
               WHERE r.event_code = c.event_code AND r.player_id = c.replaced_player_id
                 AND r.round_number > c.cut_round))
)
SELECT v.user_id, v.event_code, v.slot, v.from_round,
       coalesce(lead(v.from_round) OVER slot_rows - 1, 32767) AS to_round,
       v.player_id,
       CASE WHEN v.pick_order = 2 THEN v.replaced_player_id END AS replaced_player_id,
       v.updated_at
FROM valid v
WINDOW slot_rows AS (PARTITION BY v.user_id, v.event_code, v.slot ORDER BY v.from_round)
"""

SLOT_ROUND_POINTS_SQL = """
CREATE OR REPLACE VIEW fantasy_slot_round_points WITH (security_invoker = true) AS
SELECT ep.user_id, ep.event_code, ep.slot, ep.from_round, ep.to_round, ep.player_id, ep.replaced_player_id,
       r.round_number, r.stage,
       CASE WHEN r.round_number IS NULL THEN NULL
            WHEN r.round_number <= e.cut_round THEN 1
            WHEN r.round_number <= e.swiss_rounds THEN 2
            ELSE 3 END AS day,
       coalesce(CASE r.stage
           WHEN 'swiss' THEN
               (CASE r.result WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END)
               * CASE ep.slot
                     WHEN 'captain' THEN 2
                     WHEN 'drafter' THEN CASE r.format WHEN 'draft' THEN 3 ELSE 0 END
                     WHEN 'constructed' THEN CASE r.format WHEN 'draft' THEN 0 ELSE 2 END
                     ELSE 1 END
           WHEN 'quarterfinal' THEN 4 + CASE r.result WHEN 'W' THEN 4 ELSE 0 END
           WHEN 'semifinal' THEN CASE r.result WHEN 'W' THEN 4 ELSE 0 END
           ELSE CASE r.result WHEN 'W' THEN 8 ELSE 0 END
       END, 0) AS points
FROM fantasy_effective_picks ep
JOIN fantasy_events e ON e.code = ep.event_code
LEFT JOIN fantasy_results r ON r.event_code = ep.event_code AND r.player_id = ep.player_id
     AND r.round_number BETWEEN ep.from_round AND ep.to_round
"""

BRACKET_POINTS_SQL = """
CREATE OR REPLACE VIEW fantasy_bracket_points WITH (security_invoker = true) AS
WITH actual AS (
    SELECT r.event_code, r.bracket_position AS position, r.player_id AS winner_id,
           r.game_wins || '-' || r.game_losses AS games
    FROM fantasy_results r
    WHERE r.bracket_position IS NOT NULL AND r.result = 'W'
)
SELECT b.user_id, b.event_code, b.position, b.winner_id, b.games, b.updated_at,
       a.winner_id IS NOT NULL AS decided,
       coalesce(a.winner_id = b.winner_id, false) AS correct_winner,
       coalesce(a.winner_id = b.winner_id AND a.games = b.games, false) AS exact_games,
       CASE WHEN a.winner_id = b.winner_id THEN
                CASE WHEN b.position LIKE 'QF%' THEN 2 WHEN b.position LIKE 'SF%' THEN 4 ELSE 8 END
                + CASE WHEN a.games = b.games THEN 1 ELSE 0 END
            ELSE 0 END AS points
FROM fantasy_bracket_picks b
LEFT JOIN actual a ON a.event_code = b.event_code AND a.position = b.position
"""

MEMBER_SCORES_SQL = """
CREATE OR REPLACE VIEW fantasy_member_scores WITH (security_invoker = true) AS
WITH members AS (
    SELECT user_id, event_code, max(updated_at) FILTER (WHERE from_round = 1) AS lineup_saved_at
    FROM fantasy_picks
    GROUP BY user_id, event_code
), lineup AS (
    SELECT user_id, event_code,
           sum(points) AS points,
           sum(points) FILTER (WHERE day = 1) AS day1_points,
           sum(points) FILTER (WHERE day = 2) AS day2_points,
           sum(points) FILTER (WHERE day = 3) AS day3_points
    FROM fantasy_slot_round_points
    GROUP BY user_id, event_code
), bracket AS (
    SELECT user_id, event_code, sum(points) AS points,
           bool_or(position = 'F' AND correct_winner) AS champion_called
    FROM fantasy_bracket_points
    GROUP BY user_id, event_code
)
SELECT m.user_id, m.event_code, m.lineup_saved_at,
       (coalesce(l.points, 0) + coalesce(b.points, 0))::int AS points,
       coalesce(l.day1_points, 0)::int AS day1_points,
       coalesce(l.day2_points, 0)::int AS day2_points,
       (coalesce(l.day3_points, 0) + coalesce(b.points, 0))::int AS day3_points,
       coalesce(b.points, 0)::int AS bracket_points,
       coalesce(b.champion_called, false) AS champion_called
FROM members m
LEFT JOIN lineup l ON l.user_id = m.user_id AND l.event_code = m.event_code
LEFT JOIN bracket b ON b.user_id = m.user_id AND b.event_code = m.event_code
"""

PUBLIC_PLAYERS_SQL = """
CREATE OR REPLACE VIEW public_fantasy_players AS
SELECT p.id, p.event_code, p.slug, p.first_name, p.last_name, p.short_name, p.country, p.country_code,
       p.sources, p.photo_url, p.deck_name, p.decklist_id
FROM fantasy_players p
"""

PUBLIC_RESULTS_SQL = """
CREATE OR REPLACE VIEW public_fantasy_results AS
SELECT r.event_code, r.round_number, r.player_id, r.opponent_id, r.stage, r.format, r.result,
       r.game_wins, r.game_losses, r.game_draws, r.is_bye, r.bracket_position,
       CASE WHEN r.round_number <= e.cut_round THEN 1
            WHEN r.round_number <= e.swiss_rounds THEN 2
            ELSE 3 END AS day
FROM fantasy_results r
JOIN fantasy_events e ON e.code = r.event_code
"""

PUBLIC_STANDINGS_SQL = f"""
CREATE OR REPLACE VIEW public_fantasy_standings AS
SELECT m.event_code,
       {MEMBER_KEY} AS member_key,
       {VIEWER_IS_MEMBER} AS is_me,
       coalesce(v.name, 'Anonymous entrant') AS name,
       v.avatar_url,
       m.points, m.day1_points, m.day2_points, m.day3_points, m.bracket_points, m.champion_called,
       rank() OVER (
           PARTITION BY m.event_code
           ORDER BY m.points DESC, m.champion_called DESC, m.lineup_saved_at ASC NULLS LAST
       )::int AS rank,
       rank() OVER (PARTITION BY m.event_code ORDER BY m.day1_points DESC)::int AS day1_rank,
       rank() OVER (PARTITION BY m.event_code ORDER BY m.day2_points DESC)::int AS day2_rank,
       rank() OVER (PARTITION BY m.event_code ORDER BY m.day3_points DESC)::int AS day3_rank,
       count(*) OVER (PARTITION BY m.event_code)::int AS member_count
FROM fantasy_member_scores m
JOIN fantasy_events e ON e.code = m.event_code
LEFT JOIN fantasy_members v ON v.user_id = m.user_id
WHERE now() >= e.picks_lock_at
"""

PUBLIC_LINEUPS_SQL = f"""
CREATE OR REPLACE VIEW public_fantasy_lineups AS
SELECT m.event_code,
       {MEMBER_KEY} AS member_key,
       {VIEWER_IS_MEMBER} AS is_me,
       m.slot, m.from_round, m.to_round, m.player_id, m.replaced_player_id,
       sum(m.points)::int AS points,
       coalesce(sum(m.points) FILTER (WHERE m.day = 1), 0)::int AS day1_points,
       coalesce(sum(m.points) FILTER (WHERE m.day = 2), 0)::int AS day2_points,
       coalesce(sum(m.points) FILTER (WHERE m.day = 3), 0)::int AS day3_points
FROM fantasy_slot_round_points m
JOIN fantasy_events e ON e.code = m.event_code
WHERE now() >= e.picks_lock_at
GROUP BY m.event_code, m.user_id, m.slot, m.from_round, m.to_round, m.player_id, m.replaced_player_id
"""

PUBLIC_BRACKET_PICKS_SQL = f"""
CREATE OR REPLACE VIEW public_fantasy_bracket_picks AS
SELECT m.event_code,
       {MEMBER_KEY} AS member_key,
       {VIEWER_IS_MEMBER} AS is_me,
       m.position, m.winner_id, m.games, m.decided, m.correct_winner, m.exact_games, m.points
FROM fantasy_bracket_points m
JOIN fantasy_events e ON e.code = m.event_code
WHERE now() >= e.bracket_lock_at
"""

PUBLIC_EVENT_STATE_SQL = """
CREATE OR REPLACE VIEW public_fantasy_event_state AS
SELECT e.code AS event_code, e.revealed_through_round,
       (SELECT max(r.round_number) FROM fantasy_rounds r WHERE r.event_code = e.code) AS completed_through_round,
       e.picks_lock_at, e.day_two_started_at, e.bracket_lock_at, e.top8_started_at, e.synced_at
FROM fantasy_events e
"""

PICK_WINDOW_SQL = """
CREATE OR REPLACE FUNCTION fantasy_pick_window_open(p_event text, p_from_round int, p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN p_from_round = 1 THEN p_at < e.picks_lock_at
        WHEN p_from_round = e.cut_round + 1 THEN
            p_at >= e.picks_lock_at AND (e.day_two_started_at IS NULL OR p_at < e.day_two_started_at)
        ELSE false
    END
    FROM fantasy_events e
    WHERE e.code = p_event
$$
"""

BRACKET_WINDOW_SQL = """
CREATE OR REPLACE FUNCTION fantasy_bracket_window_open(p_event text, p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT coalesce(e.revealed_through_round, 0) >= e.swiss_rounds AND p_at < e.bracket_lock_at
           AND (e.top8_started_at IS NULL OR p_at < e.top8_started_at)
    FROM fantasy_events e
    WHERE e.code = p_event
$$
"""

CHECK_WINDOW_SQL = """
CREATE OR REPLACE FUNCTION fantasy_check_pick_window()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_user <> 'authenticated' THEN
        RETURN coalesce(NEW, OLD);
    END IF;
    IF TG_TABLE_NAME = 'fantasy_picks' THEN
        IF TG_OP IN ('UPDATE', 'DELETE')
           AND NOT coalesce(fantasy_pick_window_open(OLD.event_code, OLD.from_round, now()), false) THEN
            RAISE EXCEPTION 'fantasy picks are locked' USING ERRCODE = 'check_violation';
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE')
           AND NOT coalesce(fantasy_pick_window_open(NEW.event_code, NEW.from_round, now()), false) THEN
            RAISE EXCEPTION 'fantasy picks are locked' USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        IF TG_OP IN ('UPDATE', 'DELETE')
           AND NOT coalesce(fantasy_bracket_window_open(OLD.event_code, now()), false) THEN
            RAISE EXCEPTION 'fantasy bracket picks are locked' USING ERRCODE = 'check_violation';
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE')
           AND NOT coalesce(fantasy_bracket_window_open(NEW.event_code, now()), false) THEN
            RAISE EXCEPTION 'fantasy bracket picks are locked' USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN coalesce(NEW, OLD);
END;
$$
"""

WINDOW_TRIGGERS_SQL = """
DROP TRIGGER IF EXISTS fantasy_picks_window ON fantasy_picks;
CREATE TRIGGER fantasy_picks_window BEFORE INSERT OR UPDATE OR DELETE ON fantasy_picks
    FOR EACH ROW EXECUTE FUNCTION fantasy_check_pick_window();
DROP TRIGGER IF EXISTS fantasy_bracket_picks_window ON fantasy_bracket_picks;
CREATE TRIGGER fantasy_bracket_picks_window BEFORE INSERT OR UPDATE OR DELETE ON fantasy_bracket_picks
    FOR EACH ROW EXECUTE FUNCTION fantasy_check_pick_window();
"""

VIEW_STATEMENTS = (
    EFFECTIVE_PICKS_SQL,
    SLOT_ROUND_POINTS_SQL,
    BRACKET_POINTS_SQL,
    MEMBER_SCORES_SQL,
    PUBLIC_PLAYERS_SQL,
    PUBLIC_RESULTS_SQL,
    PUBLIC_STANDINGS_SQL,
    PUBLIC_LINEUPS_SQL,
    PUBLIC_BRACKET_PICKS_SQL,
    PUBLIC_EVENT_STATE_SQL,
    PICK_WINDOW_SQL,
    BRACKET_WINDOW_SQL,
    CHECK_WINDOW_SQL,
    WINDOW_TRIGGERS_SQL,
)

DISPLAY_NAME = """coalesce(
    nullif(u.raw_user_meta_data->'custom_claims'->>'global_name', ''),
    nullif(u.raw_user_meta_data->>'full_name', ''),
    nullif(u.raw_user_meta_data->>'user_name', ''),
    'Anonymous entrant'
)"""


def upgrade() -> None:
    op.create_table(
        "fantasy_events",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("melee_tournament_id", sa.Integer(), nullable=False),
        sa.Column("picks_lock_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("swiss_rounds", sa.SmallInteger(), nullable=False),
        sa.Column("cut_round", sa.SmallInteger(), nullable=False),
        sa.Column("draft_rounds", postgresql.ARRAY(sa.SmallInteger()), nullable=False, server_default="{}"),
        sa.Column("bracket_lock_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revealed_through_round", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("day_two_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("top8_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "fantasy_players",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_code", sa.Text(), sa.ForeignKey("fantasy_events.code", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("country_code", sa.Text(), nullable=True),
        sa.Column("sources", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("melee_username", sa.Text(), nullable=True),
        sa.Column("deck_name", sa.Text(), nullable=True),
        sa.Column("decklist_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_code", "slug"),
        sa.UniqueConstraint("event_code", "id"),
        sa.UniqueConstraint("event_code", "melee_username"),
    )
    op.create_table(
        "fantasy_results",
        sa.Column("event_code", sa.Text(), nullable=False),
        sa.Column("round_number", sa.SmallInteger(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("opponent_id", sa.Integer(), nullable=True),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("game_wins", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("game_losses", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("game_draws", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("is_bye", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("bracket_position", sa.Text(), nullable=True),
        sa.Column("melee_match_guid", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("event_code", "round_number", "player_id"),
        sa.ForeignKeyConstraint(
            ["event_code", "player_id"], ["fantasy_players.event_code", "fantasy_players.id"], ondelete="CASCADE",
        ),
        sa.CheckConstraint("result IN ('W', 'L', 'D')", name="fantasy_result_valid"),
        sa.CheckConstraint(
            "stage IN ('swiss', 'quarterfinal', 'semifinal', 'final')", name="fantasy_result_stage_valid",
        ),
        sa.CheckConstraint("format IN ('draft', 'constructed')", name="fantasy_result_format_valid"),
    )
    op.create_index("ix_fantasy_results_player", "fantasy_results", ["event_code", "player_id"])
    op.create_table(
        "fantasy_picks",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_code", sa.Text(), nullable=False),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("from_round", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "event_code", "slot", "from_round"),
        sa.ForeignKeyConstraint(
            ["event_code", "player_id"], ["fantasy_players.event_code", "fantasy_players.id"], ondelete="CASCADE",
        ),
        sa.CheckConstraint("slot IN ('captain', 'drafter', 'constructed', 'player')", name="fantasy_pick_slot_valid"),
        sa.CheckConstraint("from_round >= 1", name="fantasy_pick_from_round_valid"),
    )
    op.create_table(
        "fantasy_bracket_picks",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_code", sa.Text(), nullable=False),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("winner_id", sa.Integer(), nullable=False),
        sa.Column("games", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "event_code", "position"),
        sa.ForeignKeyConstraint(
            ["event_code", "winner_id"], ["fantasy_players.event_code", "fantasy_players.id"], ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "position IN ('QF1', 'QF2', 'QF3', 'QF4', 'SF1', 'SF2', 'F')", name="fantasy_bracket_position_valid",
        ),
        sa.CheckConstraint("games IN ('3-0', '3-1', '3-2')", name="fantasy_bracket_games_valid"),
    )
    op.create_table(
        "fantasy_rounds",
        sa.Column("event_code", sa.Text(), sa.ForeignKey("fantasy_events.code", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.SmallInteger(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_code", "round_number"),
    )
    op.create_table(
        "fantasy_members",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
    )

    for table in PRIVATE_TABLES + MEMBER_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    for statement in VIEW_STATEMENTS:
        op.execute(statement)
    op.execute(_member_access_sql())
    op.execute(_site_grants_sql())


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS fantasy_picks_sync_member ON fantasy_picks;")
    op.execute("DROP TRIGGER IF EXISTS fantasy_bracket_picks_sync_member ON fantasy_bracket_picks;")
    op.execute("DROP FUNCTION IF EXISTS sync_fantasy_member();")
    op.execute("DROP TRIGGER IF EXISTS fantasy_picks_window ON fantasy_picks;")
    op.execute("DROP TRIGGER IF EXISTS fantasy_bracket_picks_window ON fantasy_bracket_picks;")
    op.execute("DROP FUNCTION IF EXISTS fantasy_check_pick_window();")
    op.execute("DROP FUNCTION IF EXISTS fantasy_pick_window_open(text, int, timestamptz);")
    op.execute("DROP FUNCTION IF EXISTS fantasy_bracket_window_open(text, timestamptz);")
    for view in reversed(INTERNAL_VIEWS + PUBLIC_VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {view};")
    for table in ("fantasy_members", "fantasy_bracket_picks", "fantasy_picks", "fantasy_rounds", "fantasy_results",
                  "fantasy_players", "fantasy_events"):
        op.drop_table(table)


def _member_access_sql() -> str:
    policies = []
    for table in MEMBER_TABLES:
        for action, clause in (
            ("select", "USING (auth.uid() = user_id)"),
            ("insert", "WITH CHECK (auth.uid() = user_id)"),
            ("update", "USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"),
            ("delete", "USING (auth.uid() = user_id)"),
        ):
            policies.append(f'DROP POLICY IF EXISTS "{table}_{action}" ON {table};')
            policies.append(f'CREATE POLICY "{table}_{action}" ON {table} FOR {action.upper()} {clause};')
    triggers = []
    for table in MEMBER_TABLES:
        triggers.append(f"DROP TRIGGER IF EXISTS {table}_sync_member ON {table};")
        triggers.append(
            f"CREATE TRIGGER {table}_sync_member AFTER INSERT OR UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION sync_fantasy_member();"
        )
    policy_block = "\n                ".join(policies)
    trigger_block = "\n                ".join(triggers)
    return f"""
        DO $$
        DECLARE has_auth boolean;
        BEGIN
            SELECT EXISTS(
                SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'auth' AND p.proname = 'uid'
            ) INTO has_auth;

            IF has_auth THEN
                {policy_block}

                CREATE OR REPLACE FUNCTION sync_fantasy_member()
                RETURNS trigger
                LANGUAGE plpgsql
                SECURITY DEFINER
                SET search_path = public, auth
                AS $fn$
                BEGIN
                    INSERT INTO public.fantasy_members (user_id, name, avatar_url)
                    SELECT u.id, {DISPLAY_NAME}, u.raw_user_meta_data->>'avatar_url'
                    FROM auth.users u
                    WHERE u.id = NEW.user_id
                    ON CONFLICT (user_id) DO UPDATE
                        SET name = EXCLUDED.name, avatar_url = EXCLUDED.avatar_url;
                    RETURN NEW;
                END;
                $fn$;

                {trigger_block}
            END IF;
        END $$;
    """


def _site_grants_sql() -> str:
    statements = []
    for role in ("anon", "authenticated"):
        for view in INTERNAL_VIEWS:
            statements.append(f"REVOKE ALL ON {view} FROM {role};")
        for view in PUBLIC_VIEWS:
            statements.append(f"GRANT SELECT ON {view} TO {role};")
    for table in MEMBER_TABLES:
        statements.append(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO authenticated;")
    body = "\n            ".join(statements)
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            {body}
            END IF;
        END $$;
    """
