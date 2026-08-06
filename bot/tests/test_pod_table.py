import asyncio
import re
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.pod_table import TableClaimView, _existing_table, _players_committed_elsewhere
from bot.services.pod_active import ACTIVE_POD_MANAGERS, ACTIVE_TABLE_VIEWS
from bot.models import MagicSet, PodDraftEvent
from bot.services.pod_drafts import (
    next_table_index,
    record_table_event,
    table_base_name,
)
from bot.services.pod_slot import pod_display_name


def _seed_source(session, *, name="MSH Pod Draft #8", set_code="MSH", pairing="swiss", seating="leaderboard"):
    magic_set = MagicSet(code=set_code, name=f"{set_code} long name", start_date=date(2026, 6, 23))
    session.add(magic_set)
    session.flush()
    source = PodDraftEvent(
        event_date=date(2026, 7, 8),
        event_time=datetime(2026, 7, 8, 23, 0, tzinfo=timezone.utc),
        set_id=magic_set.id,
        set_code=set_code,
        format_label="MSH Draft",
        name=name,
        draftmancer_session="LLU-MSH-D8",
        discord_thread_id="thread-1",
        socket_status="reminded",
        kind="tournament",
        pairing_mode=pairing,
        seating_mode=seating,
    )
    session.add(source)
    session.flush()
    return source


def _session_base(session_id: str) -> str:
    """The readable base of a Draftmancer session id, asserting the unguessable 4-letter random tail."""
    match = re.match(r"^(?P<base>.+)-(?P<suffix>[a-z]{4})$", session_id)
    assert match is not None, f"{session_id!r} lacks a 4-letter suffix"
    return match["base"]


def test_table_base_name_strips_trailing_table():
    assert table_base_name("MSH Pod Draft #8 - Jun 8 - Table 2") == "MSH Pod Draft #8 - Jun 8"
    assert table_base_name("MSH Pod Draft #8 Table 2") == "MSH Pod Draft #8"
    assert table_base_name("MSH Pod Draft #8") == "MSH Pod Draft #8"
    assert table_base_name("SOS Pod Draft #6 - Jun 3") == "SOS Pod Draft #6 - Jun 3"


def test_next_table_index_starts_at_two(session):
    _seed_source(session)

    assert next_table_index(session, "MSH Pod Draft #8") == 2


def test_record_table_event_clones_source_into_table_two(session):
    source = _seed_source(session, pairing="swiss", seating="leaderboard")

    table_two = record_table_event(session, source_event_id=source.id)

    assert table_two.name == "MSH Pod Draft #8 - Table 2"
    assert table_two.kind == "tournament"
    assert table_two.set_code == source.set_code
    assert table_two.set_id == source.set_id
    assert table_two.format_label == source.format_label
    assert table_two.event_date == source.event_date
    assert table_two.event_time == source.event_time
    assert table_two.pairing_mode == "swiss"
    assert table_two.seating_mode == "leaderboard"
    assert _session_base(table_two.draftmancer_session) == "LLU-MSH-D8-T2"


def test_second_table_advances_to_table_three(session):
    source = _seed_source(session)
    source.discord_thread_id = "thread-1"

    record_table_event(session, source_event_id=source.id)
    table_three = record_table_event(session, source_event_id=source.id)

    assert table_three.name == "MSH Pod Draft #8 - Table 3"
    assert _session_base(table_three.draftmancer_session) == "LLU-MSH-D8-T3"


def test_table_off_a_table_bases_on_the_original_pod(session):
    source = _seed_source(session)
    table_two = record_table_event(session, source_event_id=source.id)

    table_three = record_table_event(session, source_event_id=table_two.id)

    assert table_three.name == "MSH Pod Draft #8 - Table 3"


def test_format_table_materializes_as_its_own_pod(session):
    source = _seed_source(session)
    fin = MagicSet(code="FIN", name="Final Fantasy", start_date=date(2025, 6, 10))
    session.add(fin)
    session.flush()

    table = record_table_event(session, source_event_id=source.id, format_code="FIN")

    assert table.name == pod_display_name("FIN", source.event_time)
    assert " - Table" not in table.name
    assert table.set_code == "FIN"
    assert table.set_id == fin.id
    assert table.format_label is None
    assert table.pairing_mode == source.pairing_mode
    assert _session_base(table.draftmancer_session) == "LLU-MSH-D8-T2"


def test_format_table_matching_the_source_set_keeps_lineage_naming(session):
    source = _seed_source(session)

    table = record_table_event(session, source_event_id=source.id, format_code="msh")

    assert table.name == "MSH Pod Draft #8 - Table 2"
    assert table.set_id == source.set_id


def test_colliding_format_table_names_gain_an_index(session):
    source = _seed_source(session)
    session.add(MagicSet(code="FIN", name="Final Fantasy", start_date=date(2025, 6, 10)))
    session.flush()

    first = record_table_event(session, source_event_id=source.id, format_code="FIN")
    second = record_table_event(session, source_event_id=source.id, format_code="FIN")

    assert second.name == f"{first.name} #2"


@pytest.fixture
def clean_table_registry():
    ACTIVE_TABLE_VIEWS.clear()
    yield ACTIVE_TABLE_VIEWS
    ACTIVE_TABLE_VIEWS.clear()


def _claim_card(source_event_id="src-1"):
    view = TableClaimView(
        MagicMock(), source_event_id, table_index=2, source_name="MSH Pod Draft #8",
        threshold=6, lobby_channel=MagicMock(),
    )
    edit = AsyncMock()
    view.claim_message = MagicMock()
    view.claim_message.channel.get_partial_message.return_value.edit = edit
    return view, edit


def test_edit_card_goes_through_bot_token_not_interaction(clean_table_registry):
    view, edit = _claim_card()

    asyncio.run(view.refresh_card())

    view.claim_message.channel.get_partial_message.assert_called_once_with(view.claim_message.id)
    edit.assert_awaited_once()


def test_second_activate_supersedes_and_disables_the_first(clean_table_registry):
    first, first_edit = _claim_card()
    second, _ = _claim_card()

    asyncio.run(first.activate())
    asyncio.run(second.activate())

    assert first.superseded is True
    assert first._join_button.disabled is True
    assert second.superseded is False
    assert clean_table_registry["src-1"] is second
    first_edit.assert_awaited_once()


def test_superseded_card_ignores_further_claims(clean_table_registry):
    view, _ = _claim_card()
    view.superseded = True
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()

    asyncio.run(view._on_claim(interaction))

    assert view.claims == {}
    interaction.response.defer.assert_awaited_once()


def test_materialized_table_deregisters_from_the_table_registry(clean_table_registry):
    materialized, _ = _claim_card()
    asyncio.run(materialized.activate())
    materialized.materialized = True
    ACTIVE_TABLE_VIEWS.pop(materialized.source_event_id, None)

    fresh, _ = _claim_card()
    asyncio.run(fresh.activate())

    assert materialized.superseded is False
    assert clean_table_registry["src-1"] is fresh


@pytest.fixture
def clean_manager_registry():
    ACTIVE_POD_MANAGERS.clear()
    yield ACTIVE_POD_MANAGERS
    ACTIVE_POD_MANAGERS.clear()


def _live_manager(*, claimed_ids=(), table_event_ids=()):
    manager = MagicMock()
    manager.non_bot_session_names.return_value = []
    manager.claimed_discord_ids = set(claimed_ids)
    manager.table_event_ids = set(table_event_ids)
    return manager


def test_a_gathering_join_card_is_the_pods_table(clean_manager_registry, clean_table_registry):
    card, _ = _claim_card()
    asyncio.run(card.activate())

    assert _existing_table("src-1") is not None


def test_a_fired_table_is_the_pods_table(clean_manager_registry, clean_table_registry):
    ACTIVE_POD_MANAGERS["src-1"] = _live_manager(table_event_ids={"table-2"})

    assert _existing_table("src-1") is not None


def test_a_pod_with_no_table_of_its_own_is_open_to_an_offer(clean_manager_registry, clean_table_registry):
    ACTIVE_POD_MANAGERS["src-1"] = _live_manager()
    settled, _ = _claim_card()
    settled.materialized = True
    settled.thread = MagicMock()
    ACTIVE_TABLE_VIEWS["other-pod"] = settled

    assert _existing_table("src-1") is None


def test_players_at_another_table_are_committed_elsewhere(clean_manager_registry, clean_table_registry):
    ACTIVE_POD_MANAGERS["src-1"] = _live_manager(claimed_ids={"11"})
    ACTIVE_POD_MANAGERS["table-2"] = _live_manager(claimed_ids={"21", "22"})
    forming, _ = _claim_card(source_event_id="other-pod")
    forming.claims = {31: "Cara", -1: "Fixture"}
    asyncio.run(forming.activate())

    busy = asyncio.run(_players_committed_elsewhere("src-1"))

    assert busy == {"21", "22", "31"}


def test_a_settled_join_card_commits_nobody(clean_manager_registry, clean_table_registry):
    superseded, _ = _claim_card(source_event_id="other-pod")
    superseded.claims = {41: "Dara"}
    superseded.superseded = True
    ACTIVE_TABLE_VIEWS["other-pod"] = superseded

    assert asyncio.run(_players_committed_elsewhere("src-1")) == set()
