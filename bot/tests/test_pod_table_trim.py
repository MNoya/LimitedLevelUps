from bot.commands.test_group import HALL_OF_FAME
from bot.services.pod_staging import Signup
from bot.services.pod_table_trim import Seat, seats_to_remove


def test_a_shrinking_table_removes_unlinked_then_walk_ins_then_the_latest_signups():
    pinned, early, late, unconfirmed, walk_in = (_seat(name) for name in HALL_OF_FAME[:5])
    unlinked = Seat(user_id="session-unlinked", arena_name=HALL_OF_FAME[5], discord_id=None)
    roster = [
        Signup(pinned.discord_id, pinned.arena_name, True, True),
        Signup(early.discord_id, early.arena_name, True),
        Signup(late.discord_id, late.arena_name, True),
        Signup(unconfirmed.discord_id, unconfirmed.arena_name, False),
    ]
    seats = [unlinked, late, walk_in, pinned, unconfirmed, early]

    leaving = seats_to_remove(seats, roster, keep=1)

    assert leaving == [unlinked, walk_in, unconfirmed, late, early]


def test_a_pod_without_signups_removes_the_last_to_join_and_nobody_when_the_room_fits():
    first, second, third = (_seat(name) for name in HALL_OF_FAME[:3])

    leaving = seats_to_remove([first, second, third], [], keep=2)
    nobody = seats_to_remove([first, second, third], [], keep=3)

    assert (leaving, nobody) == ([third], [])


def _seat(name: str) -> Seat:
    return Seat(user_id=f"session-{name}", arena_name=name, discord_id=f"discord-{name}")
