from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import audit
from bot.commands import descriptions as desc
from bot.config import settings
from bot.discord_helpers import command_line, in_pod_chat, in_pod_coordination, posts_publicly

logger = logging.getLogger(__name__)


HELP_TITLE = "❔ Commands"

# (section_label, [(command, description), ...])
HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("🏆 Leaderboard", [
        ("/join", desc.JOIN),
        ("/leaderboard", desc.LEADERBOARD),
        ("/stats", desc.STATS),
        ("/trophy", desc.TROPHY_HELP),
        ("/opt-out", desc.OPT_OUT),
        ("/retire", desc.RETIRE),
        ("/exile", desc.EXILE),
        ("/help", desc.HELP),
    ]),
    ("🔗 Integration", [
        ("/link-17lands", desc.LINK_17LANDS),
        ("/link-arena", desc.LINK_ARENA),
    ]),
    ("🚀 Pod Drafts", [
        ("/pod-guide", desc.POD_GUIDE),
        ("/pod-schedule", desc.POD_SCHEDULE),
        ("/report-results", desc.REPORT_RESULTS),
    ]),
]

POD_HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("🚀 Pod Drafts", [
        ("/draft", desc.POD_QUEUE),
        ("!pod", desc.POD_RALLY),
        ("/pod-schedule", desc.POD_SCHEDULE),
        ("/pod-seeding", desc.POD_SEEDING),
        ("/pod-ready", desc.POD_READY),
        ("/pod-start", desc.POD_START),
        ("/pod-pause", desc.POD_PAUSE),
        ("/pod-unpause", desc.POD_UNPAUSE),
        ("/pod-settings", desc.POD_SETTINGS),
        ("/pod-team", desc.POD_TEAM),
        ("/pod-takeover", desc.POD_TAKEOVER),
        ("/report-results", desc.REPORT_RESULTS),
        ("/pod-standings", desc.POD_STANDINGS),
        ("/pod-review", desc.POD_REVIEW),
        ("/roles", desc.ROLES),
        ("/help", desc.HELP),
    ]),
    ("🔗 Integration", [
        ("/link-17lands", desc.LINK_17LANDS),
        ("/link-arena", desc.LINK_ARENA),
    ]),
    ("⚙️ Admin", [
        ("/pod-table", desc.POD_TABLE.removeprefix("[Admin] ")),
        ("/pod-restart", desc.POD_RESTART.removeprefix("[Admin] ")),
        ("/pod-champion", desc.POD_CHAMPION.removeprefix("[Admin] ")),
    ]),
]


PREFIX_HELP_TITLE = "❔ Text Commands"

PREFIX_HELP_COMMANDS: list[tuple[str, str]] = [
    ("!llu", "Link the Website"),
    ("!leaderboard", "Link the Leaderboard"),
    ("!tier-list", "Link the Tier List"),
    ("!pods", "Link the Pods page"),
    ("!evergreen", "Link the Evergreen Episodes"),
    ("!teams", "How Team Draft works"),
    ("!pod", "Rally players for a Pod Draft"),
    ("!confirm", "Confirm your seat in a Pod thread"),
    ("!voice", "Share a Voice Chat Link"),
    ("!peasant", "Peasant Cube on CubeCobra"),
    ("!sampcube", "samp's Cube on CubeCobra"),
    ("!mema", "Middle-Earth Masters on CubeCobra"),
    ("!nephew", "What is a Nephew?"),
]


# command → blockquote usage examples, each kept to one line
HELP_EXAMPLES: dict[str, list[list[str]]] = {
    "/leaderboard": [
        ["/leaderboard", "format: Premier"],
        ["/leaderboard", "color: Boros", "set: FIN"],
        ["/leaderboard", "set: ALL"],
    ],
}


class HelpView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()


def render_help_embed(sections: list[tuple[str, list[tuple[str, str]]]] = HELP_SECTIONS) -> discord.Embed:
    embed = discord.Embed(title=HELP_TITLE, color=discord.Color.green())
    for section_label, items in sections:
        lines = []
        for cmd, blurb in items:
            lines.append(command_line(cmd, blurb))
            for example in HELP_EXAMPLES.get(cmd, []):
                lines.append("> " + " ".join(f"`{chip}`" for chip in example))
        embed.add_field(name=section_label, value="\n".join(lines), inline=False)
    embed.add_field(
        name="💬 Found a bug or have any ideas?",
        value=f"Post in <#{settings.feedback_channel_id}>",
        inline=False,
    )
    return embed


def render_prefix_help_embed() -> discord.Embed:
    lines = [command_line(cmd, blurb) for cmd, blurb in PREFIX_HELP_COMMANDS]
    return discord.Embed(title=PREFIX_HELP_TITLE, description="\n".join(lines), color=discord.Color.green())


class PrefixHelpCommand(commands.HelpCommand):
    async def _send(self) -> None:
        await self.get_destination().send(embed=render_prefix_help_embed())

    async def send_bot_help(self, mapping) -> None:
        await self._send()

    async def send_command_help(self, command) -> None:
        await self._send()

    async def send_group_help(self, group) -> None:
        await self._send()

    async def send_cog_help(self, cog) -> None:
        await self._send()

    async def send_error_message(self, error) -> None:
        await self._send()


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description=desc.HELP)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def help(self, interaction: discord.Interaction) -> None:
        in_pod_context = in_pod_coordination(interaction.channel) or in_pod_chat(interaction.channel)
        sections = POD_HELP_SECTIONS if in_pod_context else HELP_SECTIONS
        audit.event("help_invoked", user_id=str(interaction.user.id))
        ephemeral = not posts_publicly(interaction)
        await interaction.response.send_message(embed=render_help_embed(sections), view=HelpView(), ephemeral=ephemeral)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
