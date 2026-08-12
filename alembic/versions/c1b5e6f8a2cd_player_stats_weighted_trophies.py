"""player_stats.weighted_trophies + expose it on public_player_format_breakdown

Revision ID: c1b5e6f8a2cd
Revises: b0a4d5e7f1ab
Create Date: 2026-08-09

"""
from alembic import op
import sqlalchemy as sa

revision = "c1b5e6f8a2cd"
down_revision = "b0a4d5e7f1ab"
branch_labels = None
depends_on = None

_FORMAT_LABEL_CASE = """CASE
    WHEN ps.format IN (
        'PremierDraft', 'ContenderDraft', 'OpenDraft_D1_Bo1',
        'PremierDraftRemixArtifacts', 'ArenaDirect_Draft', 'DraftChallenge'
    ) THEN 'Premier'
    WHEN ps.format IN (
        'TradDraft', 'OpenDraft_D1_Bo3', 'OpenDraft_D2_Bo3', 'OpenDraft_D2_Draft1_Bo3',
        'OpenDraft_D2_Draft2_Bo3', 'OpenDraft_D2_Draft2B_Bo3', 'PickTwoTradDraft',
        'DecathlonTradDraft'
    ) THEN 'Trad'
    WHEN ps.format IN (
        'Sealed', 'TradSealed', 'ArenaDirect_Sealed', 'QualifierPlayInSealed',
        'QualifierPlayInTradSealed', 'Qualifier_D1_Sealed', 'Qualifier_D2_Sealed',
        'OpenSealed_D1_Bo1', 'OpenSealed_D1_Bo3', 'OpenSealed_D2_Bo3',
        'OpenSealed_D2_Sealed1_Bo3', 'FIAB_Sealed'
    ) THEN 'Sealed'
    WHEN ps.format IN (
        'QuickDraft', 'PickTwoDraft', 'Omniscience_Draft', 'Emblem_QuickDraft',
        'DecathlonQuickDraft'
    ) THEN 'Quick'
    WHEN ps.format = 'LimitedChampionshipQualifier_Draft1' THEN 'LCQ Draft 1'
    WHEN ps.format = 'LimitedChampionshipQualifier_Draft2' THEN 'LCQ Draft 2'
    ELSE NULL
END"""


def _grant_readers(view: str) -> None:
    """Both site roles, because dropping a view drops its grants.

    A signed-in visitor queries as ``authenticated`` and everyone else as ``anon``, so granting only
    ``anon`` leaves a view that works for logged-out users and fails for logged-in ones.
    """
    for role in ("anon", "authenticated"):
        op.execute(f"GRANT SELECT ON public.{view} TO {role};")


def _breakdown_view(weighted: bool) -> str:
    weighted_select = (
        ",\n                SUM(ps.weighted_trophies)::float AS weighted_trophies" if weighted else ""
    )
    weighted_out = ", weighted_trophies" if weighted else ""
    return f"""
        CREATE VIEW public_player_format_breakdown AS
        WITH grouped AS (
            SELECT
                s.code AS set_code,
                p.slug,
                {_FORMAT_LABEL_CASE} AS format_label,
                SUM(ps.events)::int AS events,
                SUM(ps.wins)::int AS wins,
                SUM(ps.losses)::int AS losses,
                SUM(ps.trophies)::int AS trophies{weighted_select}
            FROM player_stats ps
            JOIN players p ON p.id = ps.player_id
            JOIN sets s ON s.id = ps.set_id
            WHERE p.active = true
            GROUP BY s.code, p.slug, {_FORMAT_LABEL_CASE}
        )
        SELECT set_code, slug, format_label, events, wins, losses, trophies{weighted_out}
        FROM grouped
        WHERE format_label IS NOT NULL;
    """


def upgrade() -> None:
    # The default stays. player_stats is rewritten by whichever bot version is deployed, and a
    # writer that predates this column would otherwise fail its INSERT against a NOT NULL with no
    # default. Writing 0 instead makes _aggregate fall back to the unweighted formula, so an
    # older writer degrades to the old scores rather than to zero.
    op.add_column(
        "player_stats",
        sa.Column("weighted_trophies", sa.Float(), nullable=False, server_default="0"),
    )
    op.execute("UPDATE player_stats SET weighted_trophies = trophies")

    op.execute("DROP VIEW IF EXISTS public_player_format_breakdown;")
    op.execute(_breakdown_view(weighted=True))
    _grant_readers("public_player_format_breakdown")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public_player_format_breakdown;")
    op.execute(_breakdown_view(weighted=False))
    _grant_readers("public_player_format_breakdown")
    op.drop_column("player_stats", "weighted_trophies")
