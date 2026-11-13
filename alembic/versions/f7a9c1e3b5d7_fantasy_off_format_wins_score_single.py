"""Drafter and Constructed score single in the other format's rounds

Revision ID: f7a9c1e3b5d7
Revises: e4rlyd4yst4rt
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f7a9c1e3b5d7"
down_revision: Union[str, None] = "e4rlyd4yst4rt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for statement in VIEW_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(_slot_round_points_sql(off_format_multiplier=0))


def _slot_round_points_sql(off_format_multiplier: int) -> str:
    return f"""
CREATE OR REPLACE VIEW fantasy_slot_round_points WITH (security_invoker = false) AS
SELECT ep.user_id, ep.event_code, ep.slot, ep.from_round, ep.to_round, ep.player_id, ep.replaced_player_id,
       r.round_number, r.stage,
       coalesce(CASE r.stage
           WHEN 'swiss' THEN
               (CASE r.result WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END)
               * CASE ep.slot
                     WHEN 'captain' THEN 2
                     WHEN 'drafter' THEN CASE r.format WHEN 'draft' THEN 3 ELSE {off_format_multiplier} END
                     WHEN 'constructed' THEN CASE r.format WHEN 'draft' THEN {off_format_multiplier} ELSE 2 END
                     ELSE 1 END
           WHEN 'quarterfinal' THEN 4 + CASE r.result WHEN 'W' THEN 4 ELSE 0 END
           WHEN 'semifinal' THEN CASE r.result WHEN 'W' THEN 4 ELSE 0 END
           ELSE CASE r.result WHEN 'W' THEN 8 ELSE 0 END
       END, 0) AS points
FROM fantasy_effective_picks ep
LEFT JOIN fantasy_results r ON r.event_code = ep.event_code AND r.player_id = ep.player_id
     AND r.round_number BETWEEN ep.from_round AND ep.to_round
"""


VIEW_STATEMENTS = (_slot_round_points_sql(off_format_multiplier=1),)
