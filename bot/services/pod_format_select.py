"""Discord selector for choosing a pod-draft format.

Shared by `/pod-format`, the lobby "Change Format" button, and the `!test format` preview.
Persistence is injected via the `on_apply` callback so the same view backs the live DB-write flow
and the in-memory testlobby sandbox. Format definitions live in the pure `pod_format` registry.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import discord
from discord import ui

from bot import emojis
from bot.services import pod_format_interest as fi
from bot.services.pod_format import (
    CUSTOM_FORMATS,
    SELECT_PLACEHOLDER,
    custom_formats,
    format_applied_message,
)
from bot.sets import active_set_code, recent_released_sets


ApplyFormatCallback = Callable[[discord.Interaction, str], Awaitable[str | None]]

WRITE_IN_VALUE = "__format_write_in__"


def set_select_option(
    code: str, *, label: str, description: str, default: bool = False,
) -> discord.SelectOption:
    """A set-picker row carrying the set's keyrune symbol when its app emoji is loaded. Shared by the
    /draft launcher set picker and the pod Settings format picker so both render set rows identically."""
    return discord.SelectOption(
        label=label, value=code, description=description,
        emoji=emojis.set_symbol(code), default=default,
    )


def write_in_option(label_prefix: str) -> discord.SelectOption:
    """The 'write in any set code' launcher row, shared by the /draft set picker and the Settings
    format picker so its copy stays identical; `label_prefix` is 'Set' or 'Format' to match the picker."""
    return discord.SelectOption(
        label=f"{label_prefix}: Write-in Code", value=WRITE_IN_VALUE, description="Draft any other set",
    )


def format_options(current_code: str | None) -> list[discord.SelectOption]:
    """The format dropdown options (active set + custom cubes + recent released sets + a write-in
    launcher), with the current one defaulted. Custom cubes sit right under the active set, matching
    the /draft set picker. Labels are prefixed with 'Format:' so the collapsed dropdown reads e.g.
    'Format: SOS', matching the Pairings and Seats dropdowns and the lobby footer. Unreleased upcoming
    sets are left out — they have no card pool to draft; the write-in option still drafts any set code
    the user types, so a preview draft stays possible on purpose."""
    cur = (current_code or "").upper()
    active = active_set_code()
    recent = recent_released_sets()
    known = {active} | {seed.code for seed in recent} | set(CUSTOM_FORMATS)
    options = [write_in_option("Format")]
    if cur and cur not in known:
        options.append(set_select_option(
            cur, label=f"Format: {cur}", description="Written-in set code", default=True,
        ))
    options.append(set_select_option(
        active, label=f"Format: {active}",
        description=f"Draft the latest set ({active})", default=cur in ("", active),
    ))
    for fmt in custom_formats():
        options.append(discord.SelectOption(
            label=f"Format: {fmt.label}",
            value=fmt.code,
            description=f"CubeCobra: {fmt.cube_id}",
            emoji=fi.cube_emoji(),
            default=(cur == fmt.code.upper()),
        ))
    for seed in recent:
        options.append(set_select_option(
            seed.code, label=f"Format: {seed.code}",
            description=f"Draft {seed.name}", default=(cur == seed.code),
        ))
    return options


class FormatSelectView(ui.View):
    def __init__(self, on_apply: ApplyFormatCallback, *, current_code: str | None = None) -> None:
        super().__init__(timeout=300)
        self.add_item(FormatSelect(on_apply, current_code))


class FormatSelect(ui.Select):
    def __init__(self, on_apply: ApplyFormatCallback, current_code: str | None) -> None:
        super().__init__(
            placeholder=SELECT_PLACEHOLDER, options=format_options(current_code),
            min_values=1, max_values=1,
        )
        self._on_apply = on_apply

    async def callback(self, interaction: discord.Interaction) -> None:
        code = self.values[0]
        if code == WRITE_IN_VALUE:
            await interaction.response.send_modal(FormatWriteInModal(self._apply_write_in))
            return
        await interaction.response.defer()
        await self._apply_and_refresh(interaction, code)

    async def _apply_write_in(self, interaction: discord.Interaction, code: str) -> None:
        await interaction.response.defer()
        await self._apply_and_refresh(interaction, code)

    async def _apply_and_refresh(self, interaction: discord.Interaction, code: str) -> None:
        err = await self._on_apply(interaction, code)
        if err:
            await interaction.edit_original_response(content=f"⚠️ {err}", view=None)
            return
        await interaction.edit_original_response(
            content=format_applied_message(code),
            view=FormatSelectView(self._on_apply, current_code=code),
        )


class FormatWriteInModal(ui.Modal, title="Write in a set code"):
    code = ui.TextInput(
        label="Set code",
        placeholder="e.g. MH3, FIN, DSK",
        min_length=2,
        max_length=5,
        required=True,
    )

    def __init__(self, on_code: Callable[[discord.Interaction, str], Awaitable[None]]) -> None:
        super().__init__()
        self._on_code = on_code

    async def on_submit(self, interaction: discord.Interaction) -> None:
        typed = self.code.value.strip().upper()
        if not typed.isalnum():
            await interaction.response.send_message(
                f"⚠️ `{self.code.value}` isn't a valid set code — use letters and numbers only.",
                ephemeral=True,
            )
            return
        await self._on_code(interaction, typed)
