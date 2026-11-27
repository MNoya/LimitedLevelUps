from datetime import datetime, timezone

from bot.commands.test_group import HALL_OF_FAME
from bot.models import Player, PodDraftEvent, PodDraftParticipant
from bot.services.pod_deck_correction import save_deck_edit


def test_organizer_edit_persists_and_keeps_the_original_split(session):
    event_id = _event_with_deck(session, main=[0, 1, 2], side=[3])

    result = save_deck_edit(session, event_id, 0, {"main": [0, 1, 3], "side": [2]}, "editor", staff=True)
    session.expire_all()
    deck = session.get(PodDraftEvent, event_id).draft_log["decks"][0]

    assert result == {"main": [0, 1, 3], "side": [2]}
    assert (deck["main"], deck["side"]) == ([0, 1, 3], [2])
    assert (deck["correction"]["orig_main"], deck["correction"]["orig_side"]) == ([0, 1, 2], [3])


def test_organizer_edit_refuses_cards_outside_the_pool(session):
    event_id = _event_with_deck(session, main=[0, 1, 2], side=[3])

    result = save_deck_edit(session, event_id, 0, {"main": [0, 1, 2, 3, 4], "side": []}, "editor", staff=True)
    session.expire_all()
    deck = session.get(PodDraftEvent, event_id).draft_log["decks"][0]

    assert isinstance(result, tuple) and result[1] == 400
    assert "correction" not in deck


def test_a_player_edits_only_their_own_seat(session):
    event_id = _event_with_deck(session, main=[0, 1, 2], side=[3])
    _seat_player(session, event_id, seat=0, discord_id="111")
    swap = {"main": [0, 1, 3], "side": [2]}

    own = save_deck_edit(session, event_id, 0, swap, "111", staff=False)
    other = save_deck_edit(session, event_id, 0, swap, "222", staff=False)

    assert own == swap
    assert other == ("forbidden", 403)


def _seat_player(session, event_id: str, seat: int, discord_id: str) -> None:
    name = HALL_OF_FAME[0]
    player = Player(slug=name.lower(), discord_id=discord_id, display_name=name)
    session.add(player)
    session.flush()
    session.add(PodDraftParticipant(event_id=event_id, display_name=name, player_id=player.id, seat_index=seat))
    session.commit()


def _event_with_deck(session, main: list[int], side: list[int]) -> str:
    created = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
    event = PodDraftEvent(
        event_date=created.date(), event_time=created, set_code="MH3", name="Pod",
        draftmancer_session="s1", discord_thread_id="t1", socket_status="closed", created_at=created,
        draft_log={"v": 1, "cards": [], "decks": [{"main": main, "side": side}]},
    )
    session.add(event)
    session.commit()
    return event.id
