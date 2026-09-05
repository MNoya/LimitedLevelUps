"""Team-draft board: the match surface a team pod plays on, posted in the pod thread at endDraft.

Two-part surface: a classic embed heads it with both rosters side by side (V2 has no column
primitive) and the running Wins folded into a team's column header, then a Components V2 message
holds every cross-team match of all three rounds, each with its own report button. Pairings are a
fixed rotation, so every button is live from the start — rounds are the presented cadence, not a
gate. Buttons carry the result once reported: green for a Green Team win, blurple for Blue, with the
score as the label. Each report rebuilds the whole surface from committed match rows, so concurrent
edits self-heal. Buttons are DynamicItems (match id in the custom_id), so they keep dispatching
after a bot restart.

Discord caps a V2 message at 40 components and every match Section costs three, so 3v3 and 4v4 fit
one rounds message; a 5v5 paginates into whole-round pages, and every report re-renders all of them
together along with the summary embed.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import NamedTuple

import discord
from discord import ui
from sqlalchemy import select

from bot.database import SessionLocal
from bot.discord_helpers import NBSP, ZWSP, add_two_column_field
from bot.models import PodDraftEvent, PodDraftMatch, PodDraftParticipant
from bot.services import pod_team
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_drafts import load_event_name_sync, normalize_player_name
from bot.services.pod_seating_image import octagon_text, render_octagon_png, seat_label
from bot.services.pod_tournament import (
    CLEAR_SENTINEL,
    SKIPPED_SENTINEL,
    actor_label,
    announce_round_result,
    commit_result,
    deck_recovery_scan,
    format_match_result_log,
    format_reported_result,
    format_round_announcement,
    format_round_clear_announcement,
    load_participant_displays,
    match_was_played,
    maybe_arm_deck_nudge,
    name_with_arena,
    result_needs_announcement,
    result_was_corrected,
)


log = logging.getLogger(__name__)

REPORT_BUTTON_PREFIX = "podteamreport"
REVEAL_BUTTON_PREFIX = "podteamreveal"  # per-round reveal blocks; distinct so they don't collide with
# the big block during refresh and restart rediscovery. Must not start with REPORT_BUTTON_PREFIX


class TeamBoardMember(NamedTuple):
    display: str
    arena: str | None
    record: str | None = None
    deck_colors: str | None = None


class TeamBoardData(NamedTuple):
    event_id: str
    rosters: dict[str, list[TeamBoardMember]]
    wins: dict[str, int]
    rounds: list[tuple[int, list[dict]]]
    pending: int
    finalized: bool
    seating: tuple[tuple[str, str], ...] = ()  # (display name, team) in draft-seat order


def build_board_data(
    event_id: str,
    team_rows: list[tuple[str, str]],
    matches: list[dict],
    displays: dict[str, dict],
    finalized: bool,
) -> TeamBoardData:
    """Assemble the board model from raw rows. `team_rows` is (name, team) in seat order; `matches`
    carries match_id / round / a_name / b_name / winner_name / score in round + pairing order."""
    teams: dict[str, str] = {}
    rosters: dict[str, list[TeamBoardMember]] = {pod_team.TEAM_A: [], pod_team.TEAM_B: []}
    seating: list[tuple[str, str]] = []
    for name, team in team_rows:
        key = normalize_player_name(name)
        teams[key] = team
        info = displays.get(key, {})
        member = TeamBoardMember(
            display=info.get("display_name") or name,
            arena=info.get("arena"),
            record=info.get("record"),
            deck_colors=info.get("deck_colors"),
        )
        rosters[team].append(member)
        seating.append((member.display, team))

    for m in matches:
        a_info = displays.get(normalize_player_name(m["a_name"]), {})
        b_info = displays.get(normalize_player_name(m["b_name"]), {})
        m["a_display"] = a_info.get("display_name") or m["a_name"]
        m["b_display"] = b_info.get("display_name") or m["b_name"]
        m["a_arena"] = a_info.get("arena")
        m["b_arena"] = b_info.get("arena")
        if match_was_played(m):
            m["winner_team"] = teams.get(normalize_player_name(m["winner_name"]))
        else:
            m["winner_team"] = None

    reported = [
        (normalize_player_name(m["winner_name"]), m["score"]) for m in matches if match_was_played(m)
    ]
    a_wins, b_wins = pod_team.team_match_wins(reported, teams)
    round_nums = sorted({m["round"] for m in matches})
    rounds = [(r, [m for m in matches if m["round"] == r]) for r in round_nums]
    pending = sum(1 for m in matches if not m["winner_name"])
    return TeamBoardData(
        event_id=event_id,
        rosters=rosters,
        wins={pod_team.TEAM_A: a_wins, pod_team.TEAM_B: b_wins},
        rounds=rounds,
        pending=pending,
        finalized=finalized,
        seating=tuple(seating),
    )


def load_team_board_data(event_id: str) -> TeamBoardData:
    with SessionLocal() as session:
        participant_rows = session.execute(
            select(
                PodDraftParticipant.draftmancer_name,
                PodDraftParticipant.display_name,
                PodDraftParticipant.team,
                PodDraftParticipant.record,
                PodDraftParticipant.deck_colors,
            )
            .where(PodDraftParticipant.event_id == event_id, PodDraftParticipant.team.is_not(None))
            .order_by(PodDraftParticipant.seat_index)
        ).all()
        team_rows = [(dm_name or display_name, team) for dm_name, display_name, team, _, _ in participant_rows]
        matches = [
            {
                "match_id": row.id,
                "round": row.round,
                "a_name": row.player_a_name,
                "b_name": row.player_b_name,
                "winner_name": row.winner_name,
                "score": row.score,
            }
            for row in session.execute(
                select(PodDraftMatch)
                .where(PodDraftMatch.event_id == event_id)
                .order_by(PodDraftMatch.round, PodDraftMatch.pairing_index)
            ).scalars().all()
        ]
        finalized_at = session.execute(
            select(PodDraftEvent.finalized_at).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()
    displays = load_participant_displays(event_id)
    for dm_name, display_name, _team, record, deck_colors in participant_rows:
        key = normalize_player_name(dm_name or display_name)
        displays[key] = {**displays.get(key, {}), "record": record, "deck_colors": deck_colors}
    return build_board_data(event_id, team_rows, matches, displays, finalized_at is not None)


MAX_VIEW_CHILDREN = 40
PAGE_BASE = 3     # container + the divider and progress-bar footer
ROUND_COST = 1    # round header
SECTION_COST = 3  # section + its text + accessory button

# Invisible run appended to every round header: it holds the shrink-to-fit container open to one
# fixed width, so the report buttons land at the same right edge on every round message and don't
# shift under the cursor. The header carries it (not a match line) because the header has no accessory
# button eating the right edge, so the run never wraps a match's last word. The ZWSP anchor keeps
# Discord's trailing-whitespace trim off the NBSPs; lower the count if a header ever wraps
BOARD_WIDTH_PAD = NBSP * 45 + ZWSP

PROGRESS_GAP = NBSP * 2
PROGRESS_PENDING = "🔳"
PROGRESS_SKIPPED = "⬜"

CLINCH_NOTE = "The remaining matches still count for leaderboard points"


def plan_board_pages(rounds: list[tuple[int, list[dict]]]) -> list[list[tuple[int, list[dict]]]]:
    """Pack whole rounds into per-message pages under the 40-component cap; a round never splits
    across pages. A 3v3 is a single message; 4v4 and 5v5 split their final round off."""
    pages: list[list[tuple[int, list[dict]]]] = []
    current: list[tuple[int, list[dict]]] = []
    used = PAGE_BASE
    for round_num, matches in rounds:
        cost = ROUND_COST + SECTION_COST * len(matches)
        if current and used + cost > MAX_VIEW_CHILDREN:
            pages.append(current)
            current = []
            used = PAGE_BASE
        current.append((round_num, matches))
        used += cost
    pages.append(current)
    return pages


def build_team_board_views(data: TeamBoardData) -> list["TeamBoardView"]:
    pages = plan_board_pages(data.rounds)
    return [
        TeamBoardView(data, page, include_footer=index == len(pages) - 1)
        for index, page in enumerate(pages)
    ]


def build_team_round_view(data: TeamBoardData, round_num: int) -> "TeamBoardView":
    """One round's matches as its own board message, mirroring the 8-player pod cadence: the round is
    posted on its own and its report buttons stay live until every match is in. Round 1 carries no
    footer — its three matches are the whole picture. Later rounds close with a cumulative progress
    bar (rounds 1..N, so up to 6 squares at round 2 and 9 at round 3) plus the running score, kept
    current as earlier results land. A 5v5 round still fits one message on its own."""
    round_matches: list[dict] = []
    for r, matches in data.rounds:
        if r == round_num:
            round_matches = matches
            break
    page = [(round_num, round_matches)]
    if round_num <= 1:
        return TeamBoardView(data, page, include_footer=False, button_cls=TeamRevealReportButton)
    cumulative = [(r, matches) for r, matches in data.rounds if r <= round_num]
    return TeamBoardView(
        data, page, include_footer=True, button_cls=TeamRevealReportButton, footer_scope=cumulative,
    )


class TeamBoardView(ui.LayoutView):
    """One rounds message: each round's matches as Sections whose accessory button reports (and
    later recolors to) that match's result. The footer, when present, closes with a divider + the
    match progress bar and running score; every round header carries the same invisible width pad, so
    every message lands its report buttons at one fixed right edge. The rosters + Wins live in the
    summary embed above. Build a single round with build_team_round_view, or the multi-page combined
    board with build_team_board_views."""

    def __init__(self, data: TeamBoardData, page_rounds: list[tuple[int, list[dict]]],
                 *, include_footer: bool = True, button_cls: type | None = None,
                 footer_scope: list[tuple[int, list[dict]]] | None = None) -> None:
        super().__init__(timeout=None)
        button_cls = button_cls or TeamReportButton
        self.report_custom_ids: set[str] = set()
        container = ui.Container(accent_colour=discord.Color.green())
        for round_num, matches in page_rounds:
            container.add_item(ui.TextDisplay(f"### Round {round_num}{BOARD_WIDTH_PAD}"))
            for m in matches:
                button = button_cls.for_match(m, disabled=data.finalized)
                self.report_custom_ids.add(button.custom_id)
                line = match_line(m, waiting_on=blocking_round(data, m))
                container.add_item(ui.Section(line, accessory=button))
        if include_footer:
            container.add_item(ui.Separator())
            container.add_item(ui.TextDisplay(match_progress_bar(data, footer_scope)))
        self.add_item(container)


def match_progress_bar(
    data: TeamBoardData, rounds: list[tuple[int, list[dict]]] | None = None,
) -> str:
    """One square per match in board order, pipe-joined like the Set Awards hype meter — the winning
    team's emoji, pending and skipped squares otherwise — then the running score, leader first, and
    who leads (or won, once the draft is decided). `rounds` scopes the squares to a subset (a single
    round's message shows only its own squares); the running score always reflects the whole draft.

    A draft decided with matches still open closes with the clinch note: the team result is a
    headline, but pod points are per-player records, so a dead rubber left unplayed costs its two
    players real leaderboard points."""
    icons = []
    for _, matches in (rounds if rounds is not None else data.rounds):
        for m in matches:
            icon = pod_team.TEAM_EMOJI.get(m.get("winner_team"))
            if icon is None:
                icon = PROGRESS_SKIPPED if m.get("winner_name") == SKIPPED_SENTINEL else PROGRESS_PENDING
            icons.append(icon)
    a_wins = data.wins.get(pod_team.TEAM_A, 0)
    b_wins = data.wins.get(pod_team.TEAM_B, 0)
    tail = f"{max(a_wins, b_wins)}-{min(a_wins, b_wins)}"
    status = _score_status(a_wins, b_wins, pending=data.pending)
    if status:
        tail = f"{tail}{PROGRESS_GAP}{status}"
    bar = f"{'|'.join(icons)}{PROGRESS_GAP}**{tail}**"
    if data.pending and clinched(a_wins, b_wins, data.pending):
        return f"{bar}\n-# {CLINCH_NOTE}"
    return bar


def _score_status(a_wins: int, b_wins: int, *, pending: int) -> str | None:
    """The score's trailing phrase. A side that leads by more than the matches left has clinched the
    draft, so it reads as won right then instead of waiting for the last dead rubber to report."""
    if clinched(a_wins, b_wins, pending):
        winner = pod_team.team_winner(a_wins, b_wins)
        return f"{pod_team.team_label(winner)} wins!" if winner else "Teams are tied"
    if a_wins == b_wins:
        return "Teams are tied" if a_wins else None
    leader = pod_team.TEAM_A if a_wins > b_wins else pod_team.TEAM_B
    return f"{pod_team.team_label(leader)} lead"


def clinched(a_wins: int, b_wins: int, pending: int) -> bool:
    """Whether the draft is decided: every match reported, or one side out of reach even if the other
    takes everything left. Skipped matches are not pending, so they shrink the pool the same way."""
    return pending == 0 or abs(a_wins - b_wins) > pending


def team_result_headline(data: TeamBoardData) -> str | None:
    """The 🏆 result line for a finished team pod, rebuilt from the board's win counts and rosters so
    the scheduled card keeps its headline after the live manager is gone. None while any match is still
    pending. Members are bolded since the card is an embed."""
    if data.pending > 0:
        return None
    a_wins = data.wins.get(pod_team.TEAM_A, 0)
    b_wins = data.wins.get(pod_team.TEAM_B, 0)
    winner = pod_team.team_winner(a_wins, b_wins)
    members = [f"**{member.display}**" for member in data.rosters.get(winner, [])] if winner else []
    return pod_team.draft_result_line(winner, members, a_wins, b_wins)


def build_team_summary(data: TeamBoardData) -> tuple[discord.Embed, bytes | None]:
    """The board's header message: both rosters side by side over the round-table ring the pod drafted
    from, posted once and never edited. A classic embed because V2 has no column primitive; the
    running score lives on the board's progress bar, not here. The ring is the image `/pod-seeding`
    draws, each seat tinted with its team color, returned as raw bytes so every surface repeating the
    card uploads one render."""
    embed = discord.Embed(color=discord.Color.green())
    add_team_roster_fields(embed, data.rosters)
    png = team_seating_png(data)
    if png is None:
        return embed, None
    embed.set_image(url=f"attachment://{SEATING_IMAGE_NAME}")
    return embed, png


def build_opponent_summary(data: TeamBoardData, team: str, seating_png: bytes | None) -> discord.Embed:
    """The summary card as one side sees it in their private team thread: only the team they play,
    over the same seating ring. Their own roster is the thread's member list already."""
    opponents = pod_team.other_team(team)
    embed = discord.Embed(color=discord.Color.green())
    title = f"{pod_team.team_emoji(opponents)} {pod_team.team_label(opponents)} Opponents"
    add_roster_field(embed, title, data.rosters.get(opponents, []))
    if seating_png is not None:
        embed.set_image(url=f"attachment://{SEATING_IMAGE_NAME}")
    return embed


def seating_attachment(png: bytes | None) -> discord.File | None:
    """A single-use upload handle for rendered seating bytes. Each message carrying the summary embed
    needs its own, since a sent file is consumed."""
    if png is None:
        return None
    return discord.File(io.BytesIO(png), SEATING_IMAGE_NAME)


SEATING_IMAGE_NAME = "seating.png"
RING_SIZES = (6, 8, 10)
TEAM_SEAT_COLORS = {
    pod_team.TEAM_A: (87, 242, 135),
    pod_team.TEAM_B: (114, 137, 218),
}


def team_seating_png(data: TeamBoardData) -> bytes | None:
    """The draft table as a round-table ring, seat colors matching the team emoji. None when the
    seating is missing or not a drawable ring, which leaves the summary a plain roster embed."""
    seats = list(data.seating)
    if len(seats) not in RING_SIZES:
        return None
    colors = {seat_label(display): TEAM_SEAT_COLORS[team] for display, team in seats}
    return render_octagon_png(octagon_text([display for display, _ in seats]), colors)


def add_team_roster_fields(embed: discord.Embed, rosters: dict[str, list[TeamBoardMember]]) -> None:
    """Each team as its own two-column row: blockquoted Discord names beside code Arena handles,
    closed by a spacer so the next team starts on a fresh row. Two columns keep a long name and its
    Arena handle apart instead of wrapping into each other. Shared by the board summary header and the
    team-draft lobby card so both surfaces render identically."""
    for team in (pod_team.TEAM_A, pod_team.TEAM_B):
        title = f"{pod_team.team_emoji(team)} {pod_team.team_label(team)}"
        add_roster_field(embed, title, rosters.get(team, []))


def add_roster_field(embed: discord.Embed, title: str, members: list[TeamBoardMember]) -> None:
    add_two_column_field(
        embed,
        title,
        [member.display for member in members],
        [f"`{member.arena}`" if member.arena else ZWSP for member in members],
        spacer=True,
    )


def match_line(m: dict, waiting_on: int | None = None) -> str:
    """One match. A reported match leads with the winning team's emoji and reads by display name,
    matching the progress bar; a pending matchup leads with each player's Arena handle so opponents
    can find each other in-client once the round has scrolled past the summary embed. `waiting_on`
    marks a matchup whose players are still owed a result in that earlier round, so a posted round
    never reads as fully playable when only part of it is."""
    if match_was_played(m):
        marker = pod_team.TEAM_EMOJI.get(m.get("winner_team"), "▫️")
        return f"{marker} {format_reported_result(m)}"
    if m.get("winner_name") == SKIPPED_SENTINEL:
        return f"🚫 Not played: {m['a_display']} vs {m['b_display']}"
    a = name_with_arena(m["a_display"], m.get("a_arena"))
    b = name_with_arena(m["b_display"], m.get("b_arena"))
    if waiting_on is not None:
        return f"⌛ {a} vs {b}\n-# waiting on Round {waiting_on}"
    return f"⚔️ {a} vs {b}"


def _report_button_style(m: dict) -> tuple[discord.ButtonStyle, str]:
    """(button style, label) for a match: the score on green (Green Team won) or blurple (Blue Team
    won) once reported so the colour carries the result, grey `Report` while pending."""
    if m.get("winner_team") == pod_team.TEAM_A:
        return discord.ButtonStyle.success, m.get("score") or "won"
    if m.get("winner_team") == pod_team.TEAM_B:
        return discord.ButtonStyle.primary, m.get("score") or "won"
    if m.get("winner_name") == SKIPPED_SENTINEL:
        return discord.ButtonStyle.secondary, "Not played"
    return discord.ButtonStyle.secondary, "Report"


async def _open_report_modal(interaction: discord.Interaction, match_id: str) -> None:
    """Shared click handler for both the big-block and reveal report buttons: open the report modal
    over wherever the clicker is, instead of dropping an ephemeral at the bottom of the chat."""
    state = await asyncio.to_thread(load_match_report_state, match_id)
    if state is None:
        await interaction.response.send_message(
            "This match no longer exists", ephemeral=(interaction.guild is not None),
        )
        return
    await interaction.response.send_modal(TeamReportModal(state, board_message=interaction.message))


class TeamReportButton(
    ui.DynamicItem[ui.Button], template=rf"{REPORT_BUTTON_PREFIX}:(?P<match_id>.+)",
):
    """A match's report button on the big all-rounds block. Recolors to carry the result once
    reported; clicking opens the report modal."""

    PREFIX = REPORT_BUTTON_PREFIX

    def __init__(self, match_id: str, *, style: discord.ButtonStyle = discord.ButtonStyle.secondary,
                 label: str = "Report", disabled: bool = False) -> None:
        super().__init__(ui.Button(
            style=style, label=label, disabled=disabled,
            custom_id=f"{self.PREFIX}:{match_id}",
        ))
        self.match_id = match_id

    @classmethod
    def for_match(cls, m: dict, *, disabled: bool) -> "TeamReportButton":
        style, label = _report_button_style(m)
        return cls(m["match_id"], style=style, label=label, disabled=disabled)

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: ui.Button, match: re.Match,
    ) -> "TeamReportButton":
        return cls(match["match_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _open_report_modal(interaction, self.match_id)


class TeamRevealReportButton(
    ui.DynamicItem[ui.Button], template=rf"{REVEAL_BUTTON_PREFIX}:(?P<match_id>.+)",
):
    """The same match report button, on a per-round reveal block. Its own custom-id namespace keeps
    reveals separable from the big block during refresh and restart rediscovery; the click and recolor
    behaviour are identical to TeamReportButton."""

    PREFIX = REVEAL_BUTTON_PREFIX

    def __init__(self, match_id: str, *, style: discord.ButtonStyle = discord.ButtonStyle.secondary,
                 label: str = "Report", disabled: bool = False) -> None:
        super().__init__(ui.Button(
            style=style, label=label, disabled=disabled,
            custom_id=f"{self.PREFIX}:{match_id}",
        ))
        self.match_id = match_id

    @classmethod
    def for_match(cls, m: dict, *, disabled: bool) -> "TeamRevealReportButton":
        style, label = _report_button_style(m)
        return cls(m["match_id"], style=style, label=label, disabled=disabled)

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: ui.Button, match: re.Match,
    ) -> "TeamRevealReportButton":
        return cls(match["match_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _open_report_modal(interaction, self.match_id)


def load_match_report_state(match_id: str) -> dict | None:
    with SessionLocal() as session:
        row = session.get(PodDraftMatch, match_id)
        if row is None:
            return None
        state = {
            "match_id": row.id,
            "event_id": row.event_id,
            "round": row.round,
            "pairing_index": row.pairing_index,
            "a_name": row.player_a_name,
            "b_name": row.player_b_name,
            "winner_name": row.winner_name,
            "score": row.score,
        }
    displays = load_participant_displays(state["event_id"])
    a_info = displays.get(normalize_player_name(state["a_name"]), {})
    b_info = displays.get(normalize_player_name(state["b_name"]), {})
    state["a_display"] = a_info.get("display_name") or state["a_name"]
    state["b_display"] = b_info.get("display_name") or state["b_name"]
    return state


class TeamReportModal(ui.Modal):
    """Report modal behind a board button — an overlay, so it works no matter how far the chat has
    scrolled past the board. Option values encode `match_id|winner|score` with draftmancer names
    (DB keys), same shape as the Swiss round dropdowns."""

    def __init__(self, state: dict, board_message: discord.Message) -> None:
        super().__init__(title=f"Report Round {state['round']} Match {state['pairing_index'] + 1}"[:45])
        self.board_message = board_message
        match_id = state["match_id"]
        a_disp, b_disp = state["a_display"], state["b_display"]
        a_name, b_name = state["a_name"], state["b_name"]
        values = [
            (f"{a_disp} wins: 2-0", f"{match_id}|{a_name}|2-0"),
            (f"{a_disp} wins: 2-1", f"{match_id}|{a_name}|2-1"),
            (f"{b_disp} wins: 2-1", f"{match_id}|{b_name}|2-1"),
            (f"{b_disp} wins: 2-0", f"{match_id}|{b_name}|2-0"),
            ("No Match Played", f"{match_id}|{SKIPPED_SENTINEL}|0-0"),
        ]
        if state.get("winner_name"):
            values.insert(0, ("Clear Result", f"{match_id}|{CLEAR_SENTINEL}|0-0"))
        selected = None
        if state.get("winner_name") and state.get("score"):
            selected = f"{match_id}|{state['winner_name']}|{state['score']}"
        options = [
            discord.SelectOption(label=label[:100], value=value, default=value == selected)
            for label, value in values
        ]
        self.result = ui.Select(placeholder=f"{a_disp} vs {b_disp}"[:150], options=options,
                                min_values=1, max_values=1)
        self.add_item(ui.Label(text="Result", component=self.result))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await handle_team_report(interaction, self.result.values[0], self.board_message)


async def handle_team_report(
    interaction: discord.Interaction, value: str, board_message: discord.Message | None = None,
) -> None:
    """Commit a team-pod report, then rebuild the board in place. The defer ack closes the report
    modal; the public result line is the confirmation. The last outstanding result also finalizes
    the tournament (records → pod points, winner announcement) under the manager's advance lock so
    two closing reports can't double-finalize.

    `board_message` is the page a board click came from, and only ever a hint: it seeds board
    rediscovery after a restart and supplies the result line's jump link. Omit it when the report
    arrives from somewhere other than the board, such as a `/report-results` card or a DM."""
    try:
        match_id, winner_name, score = value.split("|", 2)
    except ValueError:
        await interaction.response.send_message("Malformed result option", ephemeral=True)
        return
    try:
        await interaction.response.defer()
    except discord.HTTPException:
        log.warning("could not defer team report interaction", exc_info=True)

    result = await asyncio.to_thread(commit_result, match_id, winner_name, score)
    if result == "not_found":
        return
    event_id = result["event_id"]
    round_num = result["round"]
    event_name = await asyncio.to_thread(load_event_name_sync, event_id)
    if result.get("cleared"):
        log.info(
            f"[{event_name}] R{round_num} cleared {match_id} by {actor_label(interaction)} (team board)"
        )
    else:
        log.info(format_match_result_log(
            event_label=event_name, round_num=round_num, actor=actor_label(interaction),
            match_id=match_id, winner=winner_name, score=score, surface="team board",
        ))

    data = await asyncio.to_thread(load_team_board_data, event_id)
    match_state = _board_match(data, match_id)
    pairings_url = round_jump_url(event_id, round_num, board_message)
    if result.get("cleared"):
        if result.get("was_reported") and match_state is not None:
            await announce_round_result(
                interaction.client, event_id,
                format_round_clear_announcement(round_num, match_state, pairings_url),
            )
    elif result_needs_announcement(result):
        if match_state is not None and match_was_played(match_state):
            await announce_round_result(
                interaction.client, event_id,
                format_round_announcement(
                    round_num, match_state, pairings_url, corrected=result_was_corrected(result),
                ),
            )

    finished = [
        name for name in (result["a_name"], result["b_name"]) if _player_has_no_pending(data, name)
    ]
    if finished:
        asyncio.create_task(deck_recovery_scan(interaction.client, event_id, finished))

    if await _maybe_finalize(event_id, data):
        data = await asyncio.to_thread(load_team_board_data, event_id)
    else:
        manager = ACTIVE_POD_MANAGERS.get(event_id)
        if manager is not None:
            from bot.services.pod_team_showcase import maybe_post_team_trophy_hype

            asyncio.create_task(maybe_post_team_trophy_hype(manager))
    await refresh_board_messages(event_id, data, board_message)
    await sync_round_reveals(event_id, data, board_message, interaction.client)


def _player_has_no_pending(data: TeamBoardData, name: str) -> bool:
    for _, matches in data.rounds:
        for m in matches:
            if not m["winner_name"] and name in (m["a_name"], m["b_name"]):
                return False
    return True


def blocking_round(data: TeamBoardData, m: dict) -> int | None:
    """The earliest round still holding one of `m`'s players in an unreported match, or None when the
    match can be played now. Rounds are a presented cadence, not a gate — a player free of every
    earlier round can play ahead while their round-mates are still going."""
    a = normalize_player_name(m["a_name"])
    b = normalize_player_name(m["b_name"])
    for round_num, matches in data.rounds:
        if round_num >= m["round"]:
            break
        for prior in matches:
            if prior["winner_name"]:
                continue
            names = {normalize_player_name(prior["a_name"]), normalize_player_name(prior["b_name"])}
            if a in names or b in names:
                return round_num
    return None


def match_is_playable(data: TeamBoardData, m: dict) -> bool:
    return blocking_round(data, m) is None


def _round_has_playable_match(data: TeamBoardData, round_num: int) -> bool:
    """True when at least one match in round_num can be played now. In the fixed 3v3 rotation this
    first happens once two of the three prior-round matches are in."""
    for r, matches in data.rounds:
        if r == round_num:
            return any(match_is_playable(data, m) for m in matches)
    return False


def _round_all_reported(data: TeamBoardData, round_num: int) -> bool:
    for r, matches in data.rounds:
        if r == round_num:
            return bool(matches) and all(m["winner_name"] for m in matches)
    return False


async def sync_round_reveals(
    event_id: str, data: TeamBoardData,
    clicked_message: discord.Message | None = None, client: discord.Client | None = None,
) -> None:
    """Post and refresh the per-round reveal blocks for rounds after the first. A round's reveal is
    posted the first time one of its matches becomes playable, then re-rendered on every later report so
    its results and cumulative footer stay current. The big block stays the full board; reveals exist so
    a freshly playable round surfaces without scrolling back up. Best-effort — a reveal that fails to
    post or edit never blocks the report, which the big block already recorded."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    thread = clicked_message.channel if clicked_message is not None else await _board_channel(manager)
    if thread is None:
        return
    if manager is not None:
        reveals = manager.team_reveal_messages
    else:
        bot_user = client.user if client is not None else None
        reveals = await find_reveal_messages(thread, bot_user)
    for round_num, _matches in data.rounds:
        if round_num <= 1:
            continue
        existing = reveals.get(round_num)
        if existing is not None:
            try:
                await existing.edit(view=build_team_round_view(data, round_num))
            except discord.HTTPException:
                log.warning(f"[TEAM] reveal_edit_failed event={event_id} round={round_num}", exc_info=True)
            continue
        if _round_all_reported(data, round_num) or not _round_has_playable_match(data, round_num):
            continue
        try:
            message = await thread.send(view=build_team_round_view(data, round_num))
        except discord.HTTPException:
            log.warning(f"[TEAM] reveal_post_failed event={event_id} round={round_num}", exc_info=True)
            continue
        reveals[round_num] = message
        if manager is not None:
            manager.team_reveal_messages[round_num] = message
        log.info(f"[TEAM] reveal_posted event={event_id} round={round_num}")


async def refresh_board_messages(
    event_id: str, data: TeamBoardData, clicked_message: discord.Message | None = None,
) -> None:
    """Re-render every rounds page; the summary embed is posted once and left alone. Pages come from
    the manager's tracked refs, or are rediscovered from the thread after a restart; the clicked
    page, when there is one, is always covered."""
    views = build_team_board_views(data)
    pages = await _resolve_board_messages(event_id, clicked_message, len(views))
    for view in views:
        target = _message_for_view(view, pages)
        if target is None:
            log.warning(f"[TEAM] board_page_missing event={event_id}")
            continue
        try:
            await target.edit(view=view)
        except discord.HTTPException:
            log.warning(f"[TEAM] board_edit_failed event={event_id} message={target.id}", exc_info=True)


def _message_for_view(view: TeamBoardView, messages: list[discord.Message]) -> discord.Message | None:
    for message in messages:
        if view.report_custom_ids & message_report_ids(message):
            return message
    return None


def message_report_ids(message: discord.Message) -> set[str]:
    """Big-block report-button custom_ids in a message's component tree, walking containers, sections,
    and section accessories. Reveal buttons carry a different prefix, so they never match here."""
    return _custom_ids_with_prefix(message, REPORT_BUTTON_PREFIX)


def message_reveal_ids(message: discord.Message) -> set[str]:
    """Reveal-button custom_ids in a message's component tree — the mark of a per-round reveal block,
    distinct from the big block's report buttons."""
    return _custom_ids_with_prefix(message, REVEAL_BUTTON_PREFIX)


def _custom_ids_with_prefix(message: discord.Message, prefix: str) -> set[str]:
    found: set[str] = set()

    def walk(components) -> None:
        for component in components:
            custom_id = getattr(component, "custom_id", None)
            if custom_id and custom_id.startswith(f"{prefix}:"):
                found.add(custom_id)
            walk(getattr(component, "children", None) or [])
            accessory = getattr(component, "accessory", None)
            if accessory is not None:
                walk([accessory])

    walk(message.components)
    return found


BOARD_HISTORY_SCAN_LIMIT = 200


async def _resolve_board_messages(
    event_id: str, clicked_message: discord.Message | None, expected_pages: int,
) -> list[discord.Message]:
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is not None and len(manager.team_board_messages) >= expected_pages:
        return list(manager.team_board_messages)
    channel = clicked_message.channel if clicked_message is not None else await _board_channel(manager)
    if channel is None:
        log.warning(f"[TEAM] board_channel_unresolved event={event_id}")
        return []
    pages = await _find_board_messages(channel, clicked_message, expected_pages)
    if manager is not None and len(pages) >= expected_pages:
        manager.team_board_messages = list(pages)
    return pages


async def _board_channel(manager):
    """The pod thread the board lives in, for a report that arrived without a board page in hand."""
    return await manager._fetch_thread() if manager is not None else None


def round_jump_url(
    event_id: str, round_num: int, board_message: discord.Message | None = None,
) -> str | None:
    """Where the pod reads a team round: its reveal block once posted, else the first board page. A team
    pod never fills `round_messages`, so the Swiss round-message lookup can't answer this — without it a
    result announced from anywhere but the board would carry an unlinked round label."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is not None:
        reveal = manager.team_reveal_messages.get(round_num)
        if reveal is not None:
            return reveal.jump_url
        if manager.team_board_messages:
            return manager.team_board_messages[0].jump_url
    return board_message.jump_url if board_message is not None else None


async def _find_board_messages(
    channel, seed: discord.Message | None, expected_pages: int,
) -> list[discord.Message]:
    """Rediscover the big-block pages after a restart: the pinned first page, then a bounded history
    scan for the rest. Big-block pages are the only messages carrying report-button custom_ids (reveal
    blocks carry a different prefix), so the filter can't catch reveals or other bot messages. `seed`
    is the clicked message when the report came from the board, and joins the set only when it is
    itself a big-block page — a click may come from a reveal block, which is not one."""
    pages: dict[int, discord.Message] = {}
    if seed is not None and message_report_ids(seed):
        pages[seed.id] = seed
    try:
        for message in await channel.pins():
            if message_report_ids(message):
                pages[message.id] = message
    except (discord.HTTPException, AttributeError):
        log.warning("could not fetch pins to rediscover the team board", exc_info=True)
    if len(pages) < expected_pages:
        try:
            async for message in channel.history(limit=BOARD_HISTORY_SCAN_LIMIT):
                if message_report_ids(message):
                    pages[message.id] = message
                if len(pages) >= expected_pages:
                    break
        except (discord.HTTPException, AttributeError):
            log.warning("could not scan history to rediscover the team board", exc_info=True)
    return sorted(pages.values(), key=lambda m: m.id)


_ROUND_HEADER_RE = re.compile(r"### Round (\d+)")


async def find_reveal_messages(thread, bot_user) -> dict[int, discord.Message]:
    """Rediscover per-round reveal blocks after a restart, keyed by round. Reveal blocks are the only
    messages carrying reveal-button custom_ids; each shows exactly one round, read from its header. Used
    by the tournament rehydration sweep so reports after a restart refresh reveals instead of posting a
    duplicate."""
    out: dict[int, discord.Message] = {}
    try:
        async for message in thread.history(limit=BOARD_HISTORY_SCAN_LIMIT):
            if bot_user is not None and message.author.id != bot_user.id:
                continue
            if not message_reveal_ids(message):
                continue
            round_num = _reveal_round_of(message)
            if round_num is not None:
                out.setdefault(round_num, message)
    except (discord.HTTPException, AttributeError):
        log.warning("could not scan history to rediscover team reveals", exc_info=True)
    return out


def _reveal_round_of(message: discord.Message) -> int | None:
    for content in _text_displays(message):
        header = _ROUND_HEADER_RE.search(content)
        if header:
            return int(header.group(1))
    return None


def _text_displays(message: discord.Message) -> list[str]:
    found: list[str] = []

    def walk(components) -> None:
        for component in components:
            content = getattr(component, "content", None)
            if content:
                found.append(content)
            walk(getattr(component, "children", None) or [])

    walk(message.components)
    return found


def _board_match(data: TeamBoardData, match_id: str) -> dict | None:
    for _, matches in data.rounds:
        for m in matches:
            if m["match_id"] == match_id:
                return m
    return None


async def _maybe_finalize(event_id: str, data: TeamBoardData) -> bool:
    if data.finalized:
        return False
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if data.pending > 0:
        if manager is not None:
            await maybe_arm_deck_nudge(manager)
        return False
    if manager is None:
        log.warning(f"[TEAM] finalize.no_manager event={event_id}")
        return False
    from bot.services import pod_team_flow

    async with manager._advance_lock:
        await pod_team_flow.finalize_team_tournament(manager)
    return True
