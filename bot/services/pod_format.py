"""Pod-draft format registry — the source of truth for which formats a pod can draft.

A pod draft's format is identified by its `set_code`: a real set code (e.g. `SOS`) drafts that
set via Draftmancer's `setRestriction`, while a registered custom code (e.g. `PEASANT`) loads a
CubeCobra cube via `importCube`. The mapping lives here in code — adding a cube is a two-line edit,
same friction as rotating a set in `bot/sets.py`. Keeping the code as `set_code` means the
frontend's existing per-set filters bucket cube pods for free.

Pure data: no Discord deps, so the data layer can import `label_for` to persist the display label.
The selector UI that drives this lives in `lobby_embed.FormatSelectView`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bot.sets import ALL_SETS, active_set_code, is_known_set, set_name_for


CUBECOBRA_LIST_URL = "https://cubecobra.com/cube/list/{cube_id}"
CUSTOM_FORMAT_DIR = Path(__file__).resolve().parent.parent / "data" / "custom_formats"


@dataclass(frozen=True)
class PodFormat:
    code: str
    label: str
    cube_id: str | None
    session_slug: str
    link_text: str
    pick_label: str
    card_list_file: str | None = None
    symbol_glyph: str | None = None
    command_name: str | None = None

    @property
    def url(self) -> str:
        """Always the card list, the page a player opens to prepare for the draft."""
        return CUBECOBRA_LIST_URL.format(cube_id=self.cube_id)


PEASANT_CODE = "PEASANT"
PEASANT_LABEL = "Peasant Cube"
PEASANT_CUBE_ID = "DaneeliusPeasantAllStars"
PEASANT_SESSION_SLUG = "Peasant"
PEASANT_LINK_TEXT = "Peasant"
PEASANT_PICK_LABEL = "Daneelius' Peasant"

MEMA_CODE = "MEMA"
MEMA_LABEL = "Middle-Earth Masters"
MEMA_CUBE_ID = "MEMA"
MEMA_SESSION_SLUG = "MEMA"
MEMA_LINK_TEXT = "Middle-Earth Masters"
MEMA_PICK_LABEL = "Middle-Earth Masters"

# Registered custom pod formats, keyed by the code stored in pod_draft_events.set_code. A cube_id
# alone loads a CubeCobra cube via importCube; a card_list_file loads a Draftmancer custom card list
# whose own [Settings] block owns the layouts and color balance.
CUSTOM_FORMATS: dict[str, PodFormat] = {
    PEASANT_CODE: PodFormat(
        PEASANT_CODE, PEASANT_LABEL, PEASANT_CUBE_ID, PEASANT_SESSION_SLUG, PEASANT_LINK_TEXT,
        PEASANT_PICK_LABEL, command_name="peasant"),
    MEMA_CODE: PodFormat(
        MEMA_CODE, MEMA_LABEL, MEMA_CUBE_ID, MEMA_SESSION_SLUG, MEMA_LINK_TEXT, MEMA_PICK_LABEL,
        card_list_file="mema.txt", symbol_glyph="mema", command_name="mema"),
}

_CARD_LIST_CACHE: dict[str, str] = {}

SELECT_PLACEHOLDER = "Select a format"
FORMAT_LOCKED_MSG = "The format can't be changed once the draft has started"
def custom_formats() -> list[PodFormat]:
    return list(CUSTOM_FORMATS.values())


def format_choices() -> list[tuple[str, str]]:
    """(label, code) for a set-or-cube slash option: the active set, every other supported set newest
    first, then custom cubes. Shared by the /mock-draft and /pod-table autocompletes."""
    active = active_set_code()
    choices = [(f"{active} (current)", active)]
    for seed in reversed(ALL_SETS):
        if seed.code != active:
            choices.append((f"{seed.code} — {seed.name}", seed.code))
    for fmt in custom_formats():
        choices.append((fmt.label, fmt.code))
    return choices


def resolve_format_code(value: str | None) -> str | None:
    """Normalize a set option to a stored code, or None when it isn't a registered set/cube."""
    code = (value or active_set_code()).strip().upper()
    if is_known_set(code) or is_custom(code):
        return code
    return None


def is_custom(code: str | None) -> bool:
    return bool(code) and code.upper() in CUSTOM_FORMATS


def is_latest_set(code: str | None) -> bool:
    """Whether `code` is the set currently on rotation. An absent code means a pod on the default set."""
    if not code:
        return True
    return code.upper() == active_set_code().upper()


def cube_id_for(code: str) -> str | None:
    fmt = CUSTOM_FORMATS.get(code.upper())
    return fmt.cube_id if fmt else None


def card_list_for(code: str | None) -> str | None:
    """The Draftmancer custom card list text for a format that ships one, read once and cached. None for
    a plain set or a CubeCobra import, which route through setRestriction/importCube instead."""
    fmt = CUSTOM_FORMATS.get((code or "").upper())
    if fmt is None or fmt.card_list_file is None:
        return None
    cached = _CARD_LIST_CACHE.get(fmt.code)
    if cached is None:
        cached = (CUSTOM_FORMAT_DIR / fmt.card_list_file).read_text(encoding="utf-8")
        _CARD_LIST_CACHE[fmt.code] = cached
    return cached


def symbol_glyph_for(code: str | None) -> str | None:
    """The keyrune glyph a custom format renders its set symbol with; None falls back to the cube symbol."""
    fmt = CUSTOM_FORMATS.get((code or "").upper())
    return fmt.symbol_glyph if fmt else None


def session_slug_for(code: str | None) -> str | None:
    """Short token used in the Draftmancer session id for a custom format; None for a plain set."""
    fmt = CUSTOM_FORMATS.get(code.upper()) if code else None
    return fmt.session_slug if fmt else None


def detect_in_title(title: str) -> str | None:
    """Custom format code whose label appears in a sesh title, else None. Case-insensitive."""
    lowered = title.lower()
    for fmt in CUSTOM_FORMATS.values():
        if fmt.label.lower() in lowered:
            return fmt.code
    return None


def label_for(code: str) -> str | None:
    """Display label for a custom (cube) format; None for a plain set — its name lives in the title."""
    fmt = CUSTOM_FORMATS.get(code.upper())
    return fmt.label if fmt else None


def format_display(code: str) -> str:
    """Always-present format label for footers/cards: the cube label, or the bare set code."""
    return label_for(code) or code.upper()


def format_display_with_picks(code: str, picks_per_pack: int | None) -> str:
    """`format_display` carrying the pick count when a pod takes more than one card per pack, since that
    changes the draft enough that players need it beside the format."""
    label = format_display(code)
    if picks_per_pack is not None and picks_per_pack > 1:
        return f"{label} Pick {picks_per_pack}"
    return label


def split_format_prefix(name: str) -> tuple[str | None, str]:
    """A pod name split into the format it leads with and the rest of the name, inverting the label
    `format_display` wrote there. `(None, name)` when the name leads with something else."""
    for fmt in CUSTOM_FORMATS.values():
        if name.lower().startswith(fmt.label.lower()):
            return fmt.code, name[len(fmt.label):].lstrip()
    head, _, rest = name.partition(" ")
    if not is_known_set(head.upper()):
        return None, name
    return head.upper(), rest


def format_name(code: str) -> str:
    """The format's own name carrying no kind word: a cube's name, since the @Cube role mention beside it
    already says Cube, or a set's full name. `format_display` stays the short label for footers."""
    fmt = CUSTOM_FORMATS.get((code or "").upper())
    return fmt.pick_label if fmt is not None else set_name_for(code)


def format_short_name(code: str) -> str:
    """The format named for a sentence that supplies its own kind word, `the next Late Peasant Pod`: a
    cube's short name, since Cube would land next to Pod, or the bare set code."""
    fmt = CUSTOM_FORMATS.get((code or "").upper())
    return fmt.link_text if fmt is not None else (code or "").upper()


def format_name_link(code: str) -> str:
    """`format_name` with a cube's name linked to its CubeCobra page, so a reader can open the card list
    before signing up. A set has no list to open and stays plain text."""
    fmt = CUSTOM_FORMATS.get((code or "").upper())
    if fmt is None:
        return set_name_for(code)
    return f"[__**{fmt.pick_label}**__]({fmt.url})"


def cube_list_link(code: str | None) -> str | None:
    """The cube's CubeCobra id linked to its card list, so a reader searching the site finds the same list
    under the same name. None for a set, which has no list to open."""
    fmt = CUSTOM_FORMATS.get((code or "").upper())
    if fmt is None:
        return None
    return f"[__**{fmt.cube_id}**__]({fmt.url})"


def command_hint(code: str | None) -> str | None:
    """The `!<name>` prefix command that reprints a custom format's links, for a compact card hint."""
    fmt = CUSTOM_FORMATS.get((code or "").upper())
    if fmt is None or fmt.command_name is None:
        return None
    return f"!{fmt.command_name}"


def format_applied_message(code: str) -> str:
    return f"Format set to **{label_for(code) or code}**."


def settings_notice_marker(setting: str) -> str:
    """Substring identifying a setting's change notices, so a new notice can replace stale ones."""
    return f"set {setting} to"


def settings_notice_markers(setting: str) -> tuple[str, str]:
    """Both forms a setting's notice takes, so the next one retires the last whoever set it."""
    return settings_notice_marker(setting), f"Set **{setting}** to"


def settings_change_message(actor: str | None, setting: str, value: str,
                            *, subtext: str | None = None) -> str:
    """Public thread notice for a lobby Settings change; shared by Format and Pairings. No actor when the
    pod's own size set it, which reads as the setting moving on its own."""
    line = (f"⚙️ **{actor}** {settings_notice_marker(setting)} **{value}**" if actor
            else f"⚙️ Set **{setting}** to **{value}**")
    return f"{line}\n-# {subtext}" if subtext else line


def format_change_message(actor: str, code: str) -> str:
    """Public thread notice when the draft format changes."""
    return settings_change_message(actor, "Format", label_for(code) or code)


PICK_2_SETS = ("HOB", "MSH")


def pick_2_offered_for(code: str | None) -> bool:
    """Whether a four-player lobby on this set is offered Pick 2 Round Robin. Sets earn a place on the list
    by drafting well at two picks a pack; a mod can still set Pick 2 by hand on any pod."""
    return (code or "").upper() in PICK_2_SETS


OLDER_SET_PICK_TIMER = 75
CUBE_PICK_TIMER = 75


def default_pick_timer_for(code: str | None, *, standard: int | None = None) -> int | None:
    """Pick timer a pod defaults to when it switches to `code`: only the latest set uses `standard`.
    Older sets and cubes each carry their own longer default, so they can move apart later."""
    if is_latest_set(code):
        return standard
    if is_custom(code):
        return CUBE_PICK_TIMER
    return OLDER_SET_PICK_TIMER
