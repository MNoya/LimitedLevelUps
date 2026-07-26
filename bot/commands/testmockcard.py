"""Owner-only `!test mockcard` — preview the /mock-draft anchor card in every state.

Renders through the real `build_mock_card`, so the copy, colors, and button sets are the ones a live
mock draft posts. Render-only: no event row, no Draftmancer session, no thread.
"""
from __future__ import annotations

from discord.ext import commands

from bot.commands.test_group import HALL_OF_FAME, test_group
from bot.config import settings
from bot.services.mock_lobby_card import (
    STATE_CANCELED,
    STATE_COMPLETE,
    STATE_DRAFTING,
    STATE_OPEN,
    build_mock_card,
)
from bot.services.pod_drafts import draftmancer_url_for, pod_page_url
from bot.sets import active_set_code


EVENT_NAME_TEMPLATE = "{code} Mock Draft 5"
SESSION_ID = "LLU-Mock-Preview"


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="mockcard")
    @commands.is_owner()
    async def test_mockcard(ctx: commands.Context, set_code: str = "") -> None:
        """Owner-only. Post the mock-draft card in each lifecycle state in this channel."""
        code = (set_code or active_set_code()).upper()
        event_name = EVENT_NAME_TEMPLATE.format(code=code)
        seated = [(name.lower(), name) for name in HALL_OF_FAME[:7]]
        early = [*seated[:2], ("unlinked_seat", None)]
        cases = (
            (STATE_OPEN, [], None),
            (STATE_OPEN, early, None),
            (STATE_OPEN, [*seated, ("chapin", "Chapin")], None),
            (STATE_DRAFTING, [*seated, ("chapin", "Chapin")], None),
            (STATE_COMPLETE, [*seated, ("chapin", "Chapin")], None),
            (STATE_CANCELED, early, HALL_OF_FAME[0]),
        )
        session_url = draftmancer_url_for(SESSION_ID)
        for state, roster, canceled_by in cases:
            embed, view = build_mock_card(
                event_name=event_name, set_code=code, session_id=SESSION_ID, session_url=session_url,
                site_url=pod_page_url(event_name), roster=roster,
                max_players=settings.pod_draft_max_players, state=state,
                spectate_url=f"{session_url}&spectate=preview", canceled_by=canceled_by,
            )
            await ctx.send(embed=embed, view=view)
