"""DM the bot owner every player DM after a delay, so push notifications can be reviewed with Discord closed"""
from __future__ import annotations

import argparse
import asyncio

import discord

from bot import emojis
from bot.commands.testdms import DM_GROUPS, send_test_dms
from bot.config import settings


async def main(delay_s: int, group: str) -> None:
    client = discord.Client(intents=discord.Intents.none())
    await client.login(settings.discord_bot_token.get_secret_value())
    try:
        await emojis.load(client)
        owner = (await client.application_info()).owner
        user = await client.fetch_user(owner.id)
        print(f"sending to {user} in {delay_s}s", flush=True)
        await asyncio.sleep(delay_s)
        link_url = f"https://discord.com/channels/{settings.discord_guild_id}/{settings.pod_draft_channel_id}"
        await send_test_dms(user.send, link_url, group)
        print("sent", flush=True)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("group", nargs="?", default="", choices=("", *DM_GROUPS))
    parser.add_argument("--delay", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(main(args.delay, args.group))
