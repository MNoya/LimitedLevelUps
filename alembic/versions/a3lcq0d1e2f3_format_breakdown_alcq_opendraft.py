"""public_player_format_breakdown: route ALCQ OpenDraft formats to the LCQ buckets

17lands files the ALCQ under OpenDraft_D1_Bo1 (Day 1) and OpenDraft_D2_Bo1 (Day 2).
Move D1 from Premier into LCQ Draft 1 and add D2 to LCQ Draft 2 so the site groups,
dropdown and scoring match scoring_buckets.json and bot/scoring.py.

Revision ID: a3lcq0d1e2f3
Revises: tr4nscounts01
Create Date: 2026-09-13
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a3lcq0d1e2f3"
down_revision: Union[str, None] = "tr4nscounts01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FORMAT_LABEL_CASE_NEW = """\
CASE
    WHEN ps.format IN (
        'PremierDraft',
        'ContenderDraft',
        'PremierDraftRemixArtifacts',
        'ArenaDirect_Draft',
        'DraftChallenge'
    ) THEN 'Premier'
    WHEN ps.format IN (
        'TradDraft',
        'OpenDraft_D1_Bo3',
        'OpenDraft_D2_Bo3',
        'OpenDraft_D2_Draft1_Bo3',
        'OpenDraft_D2_Draft2_Bo3',
        'OpenDraft_D2_Draft2B_Bo3',
        'PickTwoTradDraft',
        'DecathlonTradDraft'
    ) THEN 'Trad'
    WHEN ps.format IN (
        'Sealed',
        'TradSealed',
        'ArenaDirect_Sealed',
        'QualifierPlayInSealed',
        'QualifierPlayInTradSealed',
        'Qualifier_D1_Sealed',
        'Qualifier_D2_Sealed',
        'OpenSealed_D1_Bo1',
        'OpenSealed_D1_Bo3',
        'OpenSealed_D2_Bo3',
        'OpenSealed_D2_Sealed1_Bo3',
        'FIAB_Sealed'
    ) THEN 'Sealed'
    WHEN ps.format IN (
        'QuickDraft',
        'PickTwoDraft',
        'Omniscience_Draft',
        'Emblem_QuickDraft',
        'DecathlonQuickDraft'
    ) THEN 'Quick'
    WHEN ps.format IN ('LimitedChampionshipQualifier_Draft1', 'OpenDraft_D1_Bo1') THEN 'LCQ Draft 1'
    WHEN ps.format IN ('LimitedChampionshipQualifier_Draft2', 'OpenDraft_D2_Bo1') THEN 'LCQ Draft 2'
    ELSE NULL
END"""


_FORMAT_LABEL_CASE_OLD = """\
CASE
    WHEN ps.format IN (
        'PremierDraft',
        'ContenderDraft',
        'OpenDraft_D1_Bo1',
        'PremierDraftRemixArtifacts',
        'ArenaDirect_Draft',
        'DraftChallenge'
    ) THEN 'Premier'
    WHEN ps.format IN (
        'TradDraft',
        'OpenDraft_D1_Bo3',
        'OpenDraft_D2_Bo3',
        'OpenDraft_D2_Draft1_Bo3',
        'OpenDraft_D2_Draft2_Bo3',
        'OpenDraft_D2_Draft2B_Bo3',
        'PickTwoTradDraft',
        'DecathlonTradDraft'
    ) THEN 'Trad'
    WHEN ps.format IN (
        'Sealed',
        'TradSealed',
        'ArenaDirect_Sealed',
        'QualifierPlayInSealed',
        'QualifierPlayInTradSealed',
        'Qualifier_D1_Sealed',
        'Qualifier_D2_Sealed',
        'OpenSealed_D1_Bo1',
        'OpenSealed_D1_Bo3',
        'OpenSealed_D2_Bo3',
        'OpenSealed_D2_Sealed1_Bo3',
        'FIAB_Sealed'
    ) THEN 'Sealed'
    WHEN ps.format IN (
        'QuickDraft',
        'PickTwoDraft',
        'Omniscience_Draft',
        'Emblem_QuickDraft',
        'DecathlonQuickDraft'
    ) THEN 'Quick'
    WHEN ps.format = 'LimitedChampionshipQualifier_Draft1' THEN 'LCQ Draft 1'
    WHEN ps.format = 'LimitedChampionshipQualifier_Draft2' THEN 'LCQ Draft 2'
    ELSE NULL
END"""


def _create_view(label_case: str) -> None:
    op.execute("DROP VIEW IF EXISTS public_player_format_breakdown;")
    op.execute(f"""
        CREATE VIEW public_player_format_breakdown AS
        WITH grouped AS (
            SELECT
                s.code AS set_code,
                p.slug,
                {label_case} AS format_label,
                SUM(ps.events)::int AS events,
                SUM(ps.wins)::int AS wins,
                SUM(ps.losses)::int AS losses,
                SUM(ps.trophies)::int AS trophies,
                SUM(ps.weighted_trophies) AS weighted_trophies
            FROM player_stats ps
            JOIN players p ON p.id = ps.player_id
            JOIN sets s ON s.id = ps.set_id
            WHERE p.active = true
            GROUP BY s.code, p.slug, {label_case}
        )
        SELECT set_code, slug, format_label, events, wins, losses, trophies, weighted_trophies
        FROM grouped
        WHERE format_label IS NOT NULL;
    """)
    op.execute("GRANT SELECT ON public_player_format_breakdown TO anon, authenticated;")


def upgrade() -> None:
    _create_view(_FORMAT_LABEL_CASE_NEW)


def downgrade() -> None:
    _create_view(_FORMAT_LABEL_CASE_OLD)
