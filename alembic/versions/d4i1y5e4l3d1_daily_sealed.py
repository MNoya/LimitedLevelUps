"""Daily Sealed pools, builds and public views

Revision ID: d4i1y5e4l3d1
Revises: f7a9c1e3b5d7
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "d4i1y5e4l3d1"
down_revision: Union[str, None] = "f7a9c1e3b5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PUBLIC_VIEWS = ("public_daily_sealed_pools", "public_daily_sealed_builds")

TODAY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION daily_sealed_today() RETURNS date
LANGUAGE sql STABLE
AS $$ SELECT ((now() AT TIME ZONE 'America/New_York') - interval '10 hours')::date $$;
"""

BUILD_WINDOW_SQL = """
CREATE OR REPLACE FUNCTION daily_sealed_check_build() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.day <> daily_sealed_today() THEN
        RAISE EXCEPTION 'Daily Sealed builds can only be saved for today''s pool';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS daily_sealed_builds_window ON daily_sealed_builds;
CREATE TRIGGER daily_sealed_builds_window BEFORE INSERT OR UPDATE ON daily_sealed_builds
FOR EACH ROW EXECUTE FUNCTION daily_sealed_check_build();
"""

PUBLIC_POOLS_SQL = """
CREATE OR REPLACE VIEW public_daily_sealed_pools AS
SELECT p.day,
       p.set_code,
       row_number() OVER (PARTITION BY p.set_code ORDER BY p.day)::int AS pool_number,
       p.format,
       p.cards,
       p.original_main,
       p.colors,
       p.wins,
       p.losses,
       (SELECT count(*) FROM daily_sealed_builds b WHERE b.day = p.day)::int AS build_count
FROM daily_sealed_pools p
WHERE p.day <= daily_sealed_today();
"""

PUBLIC_BUILDS_SQL = """
CREATE OR REPLACE VIEW public_daily_sealed_builds AS
SELECT b.day,
       left(encode(sha256(b.user_id::text::bytea), 'hex'), 12) AS build_key,
       b.main,
       b.basics,
       b.colors,
       b.updated_at
FROM daily_sealed_builds b
WHERE b.day <= daily_sealed_today();
"""


def upgrade() -> None:
    op.create_table(
        "daily_sealed_pools",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("set_code", sa.Text(), nullable=False),
        sa.Column("draft_event_id", sa.String(), nullable=False, unique=True),
        sa.Column("player_id", sa.String(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("cards", postgresql.JSONB(), nullable=False),
        sa.Column("original_main", postgresql.ARRAY(sa.SmallInteger()), nullable=False, server_default="{}"),
        sa.Column("colors", sa.Text(), nullable=True),
        sa.Column("wins", sa.SmallInteger(), nullable=False),
        sa.Column("losses", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "daily_sealed_builds",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "day", sa.Date(), sa.ForeignKey("daily_sealed_pools.day", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("main", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("basics", postgresql.JSONB(), nullable=False),
        sa.Column("colors", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables
                       WHERE table_schema = 'auth' AND table_name = 'users') THEN
                ALTER TABLE daily_sealed_builds
                    ADD CONSTRAINT daily_sealed_builds_user_id_fkey
                    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE daily_sealed_pools ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE daily_sealed_builds ENABLE ROW LEVEL SECURITY;")
    op.execute(TODAY_FUNCTION_SQL)
    op.execute(BUILD_WINDOW_SQL)
    op.execute(PUBLIC_POOLS_SQL)
    op.execute(PUBLIC_BUILDS_SQL)
    op.execute(_owner_policies_sql())
    op.execute(_site_grants_sql())


def downgrade() -> None:
    for view in PUBLIC_VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {view};")
    op.execute("DROP TRIGGER IF EXISTS daily_sealed_builds_window ON daily_sealed_builds;")
    op.execute("DROP FUNCTION IF EXISTS daily_sealed_check_build();")
    op.drop_table("daily_sealed_builds")
    op.drop_table("daily_sealed_pools")
    op.execute("DROP FUNCTION IF EXISTS daily_sealed_today();")


def _owner_policies_sql() -> str:
    statements = []
    for action, clause in (
        ("select", "USING (auth.uid() = user_id)"),
        ("insert", "WITH CHECK (auth.uid() = user_id)"),
        ("update", "USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)"),
        ("delete", "USING (auth.uid() = user_id)"),
    ):
        statements.append(f'DROP POLICY IF EXISTS "daily_sealed_builds_{action}" ON daily_sealed_builds;')
        statements.append(
            f'CREATE POLICY "daily_sealed_builds_{action}" ON daily_sealed_builds FOR {action.upper()} {clause};'
        )
    body = "\n                ".join(statements)
    return f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'auth' AND p.proname = 'uid'
            ) THEN
                {body}
            END IF;
        END $$;
    """


def _site_grants_sql() -> str:
    statements = []
    for role in ("anon", "authenticated"):
        for view in PUBLIC_VIEWS:
            statements.append(f"GRANT SELECT ON {view} TO {role};")
    statements.append("GRANT SELECT, INSERT, UPDATE, DELETE ON daily_sealed_builds TO authenticated;")
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
