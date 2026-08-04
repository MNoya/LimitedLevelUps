"""All player-facing copy for the Daily Pod Launcher and its rolling-signup surfaces.

One place to edit launcher wording. Genuinely cross-surface strings (the Format Preference button
label, shared with the roster reminder) stay in `bot/commands/messages.py`; custom_ids and layout
constants stay beside the code that uses them.

Plain declarative microcopy: name the real thing and the real action in the plainest accurate word,
literal compositional verbs, no phrasal verbs or idioms, no em dashes, no marketing register.
"""
from __future__ import annotations

from bot.commands.messages import MSG_PREFERENCE_LINE
from bot.discord_helpers import NBSP
from bot.services import pod_format_interest as fi


POLL_TITLE = "Daily Pod Launcher"
POLL_INTRO_TIME_ONLY = "### Choose a time to draft"
POLL_INTRO_TIME_AND_FORMAT = "### Choose a time and format to draft"
POLL_MECHANICS = (
    "▫️Pod event thread opens at **{threshold} players**\n"
    "▫️Draftmancer lobby opens **{lead} minutes before** the start time"
)
POLL_FORMAT_SEVERAL = (
    f"{NBSP}{fi.FLEXIBLE_MARKER}{NBSP}Sign up for more than one pod to play in the first one that fills"
)
POLL_CLOSED_LABEL = "🔒 Signups Closed"
ARCHIVE_INTRO = "### On This Day"
MARKER_CLOSED = "Closed"
FINISHED_MARK = "🏆"
PLAYING_MARK = "⚔️"
SECTION_NEXT = "**Next**"
PLAYED_FOLDED = f"{NBSP * 6}and {{count}} more draft{{plural}} played"
NEXT_EMOJI = "chordoHello"
MSG_ON_BOTH_PODS = "You are on both {slot} Pods: {formats}"
MSG_ON_SEVERAL_PODS = "You are on all {count} {slot} Pods: {formats}"
MSG_POD_THAT_NEEDS_YOU = "You will play the pod that needs you to fill a table"
MSG_POLL_INACTIVE = "This poll is no longer active. If this is a mistake, contact {organizer}"
MSG_SLOT_CLOSED = "This slot is closed. If this is a mistake, contact {organizer}"

BOARD_LEAVE_LABEL = "Leave"
BOARD_LEAVE_EMOJI = "❌"
MSG_ON_NO_POD = "You are not signed up for a pod"
MSG_REMOVED_FROM_PODS = "❌ Removed from your pods"

PLAY_AGAIN_LOVE_EMOJI = "chordo_love"
PLAY_AGAIN_INTRO = (
    "### {love} Thank you for playing!\n"
    "{next} Sign up for the next {pod} from here, same time tomorrow"
)
PLAY_AGAIN_BUTTON = "{pod} Tomorrow"
PLAY_AGAIN_SIGNED_UP = "✅ {player} signed up for the next {pod} Pod"

INTEREST_PLACEHOLDER = "Select your Format Preference"
INTEREST_DESC_FLASHBACK = "Any Past Set, Rank Your Favorites"
INTEREST_DESC_CUBE = "Choose from the server's cubes"
MSG_INTEREST_PROMPT = (
    "### Choose what you would prefer to draft\n"
    "**Save** your preference so the pods you like get scheduled"
)
MSG_INTEREST_SAVED = f"### ✨ Saved\n{MSG_PREFERENCE_LINE}"
SAVE_BUTTON_LABEL = "Save"
SAVE_BUTTON_EMOJI = "💾"
RANK_BUTTON_LABEL = "Rank Sets"
RANK_BUTTON_EMOJI = "📊"
RANK_MODAL_TITLE = "Rank Flashback Sets"
RANK_MODAL_FIELD = "Set Codes"
RANK_MODAL_PLACEHOLDER = "e.g. XXX YYY NEO"
RANK_MODAL_EXPLAINER = (
    f"Set your Flashback preference, best first, **up to {fi.FLASHBACK_RANKING_MAX} sets**\n\nWhen a pod opens a "
    "**Format Vote**, your sets are added to the poll options"
)
MSG_RANK_EMPTY = "No sets ranked"
CUBE_SELECT_PLACEHOLDER = "Select Cubes"
