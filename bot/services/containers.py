"""Components V2 building blocks for the announcement posts.

The Section carries the thumbnail as its accessory, so its text wraps beside the image. A short post
passes everything as `header` to keep it in that one block with no gap; a longer one passes a `body` too,
which starts below the image and runs full width instead of wrapping in the narrow column.
"""
from __future__ import annotations

import discord
from discord import ui

ACCENT = discord.Color.green()


def build_container(
    header: str, thumbnail_url: str | None, body: str | None = None, accent: discord.Color | None = None,
) -> ui.Container:
    container = ui.Container(accent_colour=accent or ACCENT)
    if thumbnail_url:
        container.add_item(ui.Section(ui.TextDisplay(header), accessory=ui.Thumbnail(media=thumbnail_url)))
    else:
        container.add_item(ui.TextDisplay(header))
    if body:
        container.add_item(ui.TextDisplay(body))
    return container


def as_view(*items: ui.Item) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    for item in items:
        view.add_item(item)
    return view
