"""Owner-only `!test champcard` — the Set Championship card with its three roster columns.

`build_rsvp_embed` supplies the title, the announcement, and the Time field, and only the roster fields
are swapped, so the preview cannot drift from the live card. Render-only: no pod, signal, or role is
created.

Variants: `under` for a roster below the seat count, `live` for the card once the draft starts, and
`done` for a finished championship. The last two show the columns surviving the phase the live card
currently overwrites them in, which is the point of keeping them: the seeding record outlives the pod.
"""
from __future__ import annotations

import discord
from discord.ext import commands

from bot.commands.pod_rsvp import CARD_STATUS_DRAFTING, DraftedPlayer, build_rsvp_embed
from bot.commands.test_group import HALL_OF_FAME, test_group
from bot.commands.testchampionship import MSG_NO_SUCCESSOR
from bot.services import championship
from bot.services import championship_copy as cc
from bot.services.championship_roster_card import ChampionshipRoster, championship_roster
from bot.services.ping_roles import SET_CHAMPION_ROLE_NAME
from bot.services.player_stats import SeededAttendee
from bot.services.pod_roles import find_role
from bot.services.pod_signals import RSVP_MAYBE, RSVP_NO, RSVP_YES

UNDER_FILLED_VARIANT = "under"
DRAFTING_VARIANT = "live"
COMPLETE_VARIANT = "done"
FULL_YES_COUNT = 16
UNDER_FILLED_YES_COUNT = 5

_PREVIEW_RECORDS = ("3-0", "2-1", "2-1", "2-1", "1-2", "1-2", "1-2", "0-3")
_PREVIEW_COLORS = ("WU", "BR", "Gw", "UB", "RG", "WB", "UR", "GW")
_PREVIEW_CHAMPION_LINE = "🏆 {name} wins the draft"

_YES_STANDINGS = (
    (4, 111, 23), (5, 82, 26), (6, 79, 21), (7, 76, 28), (9, 71, 21), (12, 56, 24), (20, 43, 15),
    (23, 41, 18), (27, 38, 14), (30, 36, 9), (63, 19, 12), (118, 6, 2), (128, 5, 3),
)
_UNRANKED_YES = 3
_MAYBE_STANDINGS = (
    (10, 67, 22), (13, 52, 20), (14, 52, 18), (22, 41, 12), (26, 38, 13), (58, 20, 3), (125, 5, 2),
)
_DECLINED_STANDINGS = (
    (1, 148, 31), (2, 133, 29), (3, 120, 25), (8, 74, 19), (11, 66, 21), (15, 50, 17), (16, 49, 16),
    (24, 40, 11), (28, 37, 12), (60, 18, 4), (130, 4, 1),
)


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="champcard")
    @commands.is_owner()
    async def test_champcard(ctx: commands.Context, variant: str = "") -> None:
        """Owner-only. Post the Set Championship card with its Top 8 / Alternates / Can't columns. Pass
        `under` for a roster below the seat count, `live` for a draft in flight, `done` for a finished one."""
        plan = championship.plan_for()
        if plan is None:
            await ctx.send(MSG_NO_SUCCESSOR)
            return
        yes_count = UNDER_FILLED_YES_COUNT if variant == UNDER_FILLED_VARIANT else FULL_YES_COUNT
        roster = _preview_roster(yes_count)
        name = f"👑 {plan.set_code} Set Championship"
        if variant in (DRAFTING_VARIANT, COMPLETE_VARIANT):
            embed = _locked_card(name, plan.event_at, plan.set_code, roster, variant)
        else:
            embed = _gathering_card(name, plan, roster, ctx.guild)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


def _gathering_card(name, plan, roster: ChampionshipRoster, guild) -> discord.Embed:
    champion_role = find_role(guild, SET_CHAMPION_ROLE_NAME) if guild else None
    card_body = cc.card_content(
        set_name=plan.set_name, set_code=plan.set_code, next_set_name=plan.next_set_name,
        next_set_code=plan.next_set_code, next_release_at=plan.next_release_at,
        champion_mention=cc.champion_role_mention(champion_role),
    )
    return build_rsvp_embed(
        name, plan.event_at, _rsvp_names(roster), set_code=plan.set_code, announcement=card_body,
        championship_roster=roster,
    )


def _locked_card(name, event_at, set_code, roster: ChampionshipRoster, variant: str) -> discord.Embed:
    """The card once the pod locks: the drafters in seat order while it runs, the final standings once it
    finishes, with the roster columns kept below either one."""
    complete = variant == COMPLETE_VARIANT
    drafters = [
        DraftedPlayer(
            display_name=a.display_name, seat_index=seat,
            deck_colors=_PREVIEW_COLORS[seat] if complete else None,
            record=_PREVIEW_RECORDS[seat] if complete else None,
            placement=seat + 1 if complete else None,
        )
        for seat, a in enumerate(roster.playing)
    ]
    champion = _PREVIEW_CHAMPION_LINE.format(name=roster.playing[0].display_name)
    return build_rsvp_embed(
        name, event_at, _rsvp_names(roster), set_code=set_code,
        status_line=champion if complete else CARD_STATUS_DRAFTING,
        locked_roster=drafters, draft_complete=complete, championship_roster=roster,
    )


def _preview_roster(yes_count: int) -> ChampionshipRoster:
    """A championship-sized roster: ranked Yes down past the cut, a few unranked at the bottom of Yes,
    Maybes that outrank some of those alternates, and a No list with top seeds in it."""
    names = iter(HALL_OF_FAME)
    yes = [_ranked(next(names), standing) for standing in _YES_STANDINGS]
    yes += [_unranked(next(names)) for _ in range(_UNRANKED_YES)]
    maybe = [_ranked(next(names), standing) for standing in _MAYBE_STANDINGS]
    declined = [_ranked(next(names), standing) for standing in _DECLINED_STANDINGS]
    return championship_roster(yes[:yes_count], maybe, declined)


def _ranked(name: str, standing: tuple[int, int, int]) -> SeededAttendee:
    rank, score, trophies = standing
    return SeededAttendee(slug=None, display_name=name, rank=rank, score=float(score), trophies=trophies)


def _unranked(name: str) -> SeededAttendee:
    return SeededAttendee(slug=None, display_name=name, rank=None, score=None, trophies=None)


def _rsvp_names(roster: ChampionshipRoster) -> dict[str, list[str]]:
    return {
        RSVP_YES: [a.display_name for a in roster.playing],
        RSVP_MAYBE: [alt.attendee.display_name for alt in roster.alternates if alt.maybe],
        RSVP_NO: [a.display_name for a in roster.declined],
    }
