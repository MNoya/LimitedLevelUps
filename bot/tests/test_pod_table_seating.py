from bot.commands.pod_second_table import table_one_leavers
from bot.commands.test_group import HALL_OF_FAME
from bot.services.pod_confirm import plan_tables
from bot.services.pod_staging import Signup
from bot.services.pod_table_seating import seat_tables
from bot.services.pod_table_trim import Seat


def test_players_in_a_room_keep_their_table_over_earlier_signups_who_are_not_in_one():
    roster = _confirmed(12)
    ids = [signup.discord_id for signup in roster]
    table_one_room = ids[4:12]
    table_two_room = [ids[3]]

    seating = seat_tables(roster, [table_one_room, table_two_room], plan_tables(12))

    assert seating.tables == [ids[4:10], [ids[3], ids[10], ids[11], ids[0], ids[1], ids[2]]]
    assert seating.waiting == []


def test_a_roster_one_table_holds_seats_in_signup_order_and_the_extra_player_waits():
    roster = _confirmed(11)
    ids = [signup.discord_id for signup in roster]

    seating = seat_tables(roster, [[], []], plan_tables(11))

    assert seating.tables == [ids[:10], []]
    assert seating.waiting == [ids[10]]


def test_table_one_sends_out_players_seated_elsewhere_then_unlinked_seats_past_its_size():
    roster = _confirmed(7)
    seats = [_seat(signup) for signup in roster]
    unlinked = [Seat("session-a", "Stranger#1", None), Seat("session-b", "Stranger#2", None)]
    keeping = [signup.discord_id for signup in roster[:5]]

    leaving = table_one_leavers(seats + unlinked, roster, keeping, size=6)

    assert leaving == [seats[5], seats[6], unlinked[1]]


def _confirmed(count: int) -> list[Signup]:
    return [Signup(f"id-{index}", HALL_OF_FAME[index % len(HALL_OF_FAME)], True) for index in range(count)]


def _seat(signup: Signup) -> Seat:
    return Seat(f"session-{signup.discord_id}", signup.display_name, signup.discord_id)
