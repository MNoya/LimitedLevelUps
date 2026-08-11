"""Submit-Deck button + ephemeral guild dropdown + write-in modal.

Pure UI; persistence is injected via callbacks so the same components back both the
testlobby preview (in-memory dict) and the live flow (DB write).

Callbacks raise NotInPodError when the caller isn't a registered participant for
the current pod — the UI then short-circuits to a polite ephemeral instead of
showing the dropdown.

Storage convention: WUBRG-sorted main colors uppercase, splash lowercase
(matches 17lands and the Pips component on the frontend). E.g. 'WU', 'URg'.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import discord
from discord import ui

from bot import emojis
from bot.commands.messages import MSG_COLOR_WRITE_IN_HINT


class NotInPodError(Exception):
    """Raised by lookup/submit callbacks when the interaction user isn't a participant."""


SubmitCallback = Callable[[discord.Interaction, str], Awaitable[None]]
LookupCallback = Callable[[discord.Interaction], Awaitable[str | None]]
OrganizerCallback = Callable[[discord.Interaction], Awaitable[bool]]


# Track the most recent ephemeral per user so we can delete it on the next button click
# (avoids the stacked-ephemeral pile-up Discord otherwise leaves behind).
_PREV_EPHEMERAL: dict[int, discord.InteractionMessage] = {}


GUILDS: list[tuple[str, str]] = [
    ("WU", "Azorius"),
    ("WB", "Orzhov"),
    ("WR", "Boros"),
    ("WG", "Selesnya"),
    ("UB", "Dimir"),
    ("UR", "Izzet"),
    ("UG", "Simic"),
    ("BR", "Rakdos"),
    ("BG", "Golgari"),
    ("RG", "Gruul"),
]
GUILD_LABEL = {code: name for code, name in GUILDS}

# Two-color Mana font emoji names — follow the color-wheel hybrid order, NOT WUBRG: WR is `manarw`,
# WG is `managw`, UG is `managu`. Keyed by frozenset so input order doesn't matter.
PAIR_EMOJI_NAME: dict[frozenset[str], str] = {
    frozenset("WU"): "manawu",
    frozenset("WB"): "manawb",
    frozenset("WR"): "manarw",
    frozenset("WG"): "managw",
    frozenset("UB"): "manaub",
    frozenset("UR"): "manaur",
    frozenset("UG"): "managu",
    frozenset("BR"): "manabr",
    frozenset("BG"): "manabg",
    frozenset("RG"): "manarg",
}
OTHER_VALUE = "__other__"

NOT_IN_POD_MSG = "You are not registered as a player in this pod"

SAVED_MSG = "Deck Color saved!"


def color_label(code: str) -> str:
    if code in GUILD_LABEL:
        return f"{GUILD_LABEL[code]} ({code})"
    return code


def format_deck_color_emojis(code: str | None) -> str:
    """Render deck color string as Mana font application emojis.

    Main colors render first using guild-pair / pentacolor / WUBRG-order rules. Splash colors
    (lowercase in `code`) render after, separated by '/'.

    - "WR"   → :manarw:                        (guild pair, no splash)
    - "URG"  → :manau::manar::manag:           (3 main, no splash)
    - "WUBRG"→ :manawubrg:                     (5 main, no splash)
    - "BGw"  → :manab::manag:/:manaw:          (BG main, W splash)
    - "URw"  → :manaur:/:manaw:                (UR guild pair main, W splash)
    """
    if not code:
        return ""
    main: set[str] = set()
    splash: set[str] = set()
    for c in code:
        u = c.upper()
        if u not in "WUBRG":
            continue
        (main if c.isupper() else splash).add(u)
    if not main and splash:
        main, splash = splash, set()
    if not main:
        return ""

    main_glyph = _emojis_for_color_set(main)
    if not splash:
        return main_glyph
    return f"{main_glyph}/{_emojis_for_color_set(splash)}"


def _emojis_for_color_set(colors: set[str]) -> str:
    if len(colors) == 2:
        emoji_name = PAIR_EMOJI_NAME.get(frozenset(colors))
        if emoji_name:
            glyph = emojis.get(emoji_name)
            if glyph:
                return glyph
    if len(colors) == 5:
        glyph = emojis.get("manawubrg")
        if glyph:
            return glyph
    out = []
    for c in "WUBRG":
        if c in colors:
            glyph = emojis.get(f"mana{c.lower()}") or c
            out.append(glyph)
    return "".join(out)


def _sanitize(raw: str) -> str | None:
    s = raw.strip()
    if not s or len(s) > 5:
        return None
    if not all(c in "WUBRGwubrg" for c in s):
        return None
    return s


class SubmitDeckView(ui.View):
    """Holds the Submit Deck button. Pass the persistence callbacks once at construction.

    For the live (persistent) registration, instantiate with DB-backed callbacks at startup
    via bot.add_view(SubmitDeckView(...)).
    """

    def __init__(
        self,
        on_submit: SubmitCallback,
        on_lookup: LookupCallback,
        on_organizer: OrganizerCallback | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.add_item(SubmitDeckButton(on_submit, on_lookup, on_organizer))


class SubmitDeckButton(ui.Button):
    def __init__(
        self,
        on_submit: SubmitCallback,
        on_lookup: LookupCallback,
        on_organizer: OrganizerCallback | None = None,
    ) -> None:
        super().__init__(
            label="Submit Colors",
            style=discord.ButtonStyle.primary,
            custom_id="poddecksubmit",
            emoji="🎨",
        )
        self._submit = on_submit
        self._lookup = on_lookup
        self._organizer = on_organizer

    async def callback(self, interaction: discord.Interaction) -> None:
        if self._organizer is not None and await self._organizer(interaction):
            return
        try:
            current_color = await self._lookup(interaction)
        except NotInPodError:
            await interaction.response.send_message(NOT_IN_POD_MSG, ephemeral=True)
            return

        prev = _PREV_EPHEMERAL.pop(interaction.user.id, None)
        if prev is not None:
            try:
                await prev.delete()
            except discord.HTTPException:
                pass

        view = DeckColorSelectView(self._submit, current_value=current_color)
        await interaction.response.send_message(view=view, ephemeral=True)
        try:
            _PREV_EPHEMERAL[interaction.user.id] = await interaction.original_response()
        except discord.HTTPException:
            pass


LIVE_COLOR_CUSTOM_ID = "poddeckselect-color"


def _dm_ephemeral(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None


def _build_color_options(current_value: str | None) -> list[discord.SelectOption]:
    guild_codes = {code for code, _ in GUILDS}
    is_write_in = current_value is not None and current_value not in guild_codes
    options = [discord.SelectOption(
        label=f"Other ({current_value})" if is_write_in else "Other (write-in)",
        value=OTHER_VALUE,
        description=MSG_COLOR_WRITE_IN_HINT,
        emoji=emojis.get_emoji("manax"),
        default=is_write_in,
    )]
    options.extend(
        discord.SelectOption(
            label=f"{name} ({code})",
            value=code,
            default=(current_value == code),
            emoji=emojis.get_emoji(PAIR_EMOJI_NAME[frozenset(code)]),
        )
        for code, name in GUILDS
    )
    return options


async def _report_not_in_pod(interaction: discord.Interaction, *, persistent: bool) -> None:
    if persistent:
        await interaction.followup.send(NOT_IN_POD_MSG, ephemeral=_dm_ephemeral(interaction))
    else:
        await interaction.edit_original_response(content=NOT_IN_POD_MSG, view=None)


class DeckColorSelectView(ui.View):
    """Deck-color dropdown. The default ephemeral form is one-shot and re-renders itself in place after a
    save. persistent=True is the DM direct-dropdown flow: a stable custom_id so it survives restarts, and
    the select stays silent on save so the parent module's refresh helper re-renders the message."""

    def __init__(
        self, on_submit: SubmitCallback, current_value: str | None = None, *, persistent: bool = False,
    ) -> None:
        super().__init__(timeout=None if persistent else 300)
        self.add_item(DeckColorSelect(on_submit, current_value, persistent=persistent))


class DeckColorSelect(ui.Select):
    def __init__(
        self, on_submit: SubmitCallback, current_value: str | None, *, persistent: bool = False,
    ) -> None:
        super().__init__(
            custom_id=LIVE_COLOR_CUSTOM_ID if persistent else discord.utils.MISSING,
            placeholder="Choose your deck colors",
            options=_build_color_options(current_value),
            min_values=1, max_values=1,
        )
        self._submit = on_submit
        self._persistent = persistent

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0]
        if value == OTHER_VALUE:
            await interaction.response.send_modal(DeckColorWriteInModal(self._submit, persistent=self._persistent))
            return
        await interaction.response.defer()
        try:
            await self._submit(interaction, value)
        except NotInPodError:
            await _report_not_in_pod(interaction, persistent=self._persistent)
            return
        if not self._persistent:
            await interaction.edit_original_response(
                content=SAVED_MSG,
                view=DeckColorSelectView(self._submit, current_value=value),
            )


class DeckColorWriteInModal(ui.Modal, title="Deck colors"):
    colors = ui.TextInput(
        label="Colors (e.g. URg, WUBR, WUBRG)",
        placeholder="Uppercase = main, lowercase = splash",
        min_length=1,
        max_length=5,
        required=True,
    )

    def __init__(self, on_submit: SubmitCallback, *, persistent: bool = False) -> None:
        super().__init__()
        self._submit = on_submit
        self._persistent = persistent

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cleaned = _sanitize(self.colors.value)
        if cleaned is None:
            await self._report_invalid(interaction)
            return
        await interaction.response.defer()
        try:
            await self._submit(interaction, cleaned)
        except NotInPodError:
            await _report_not_in_pod(interaction, persistent=self._persistent)
            return
        if not self._persistent:
            await interaction.edit_original_response(
                content=SAVED_MSG,
                view=DeckColorSelectView(self._submit, current_value=cleaned),
            )

    async def _report_invalid(self, interaction: discord.Interaction) -> None:
        warning = f"⚠️ `{self.colors.value}` isn't valid — use only W/U/B/R/G letters, 1–5 chars."
        if self._persistent:
            await interaction.response.send_message(warning, ephemeral=_dm_ephemeral(interaction))
        else:
            await interaction.response.edit_message(
                content=warning,
                view=DeckColorSelectView(self._submit, current_value=None),
            )
