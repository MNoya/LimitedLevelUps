from bot.services.pod_card_extract import extract_event_rows


def _compact() -> dict:
    return {
        "seats": ["Alice", "Bob"],
        "cards": [{"n": f"c{i}", "s": "PEA"} for i in range(12)],
        "packs": [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [10, 11]],
        "picks": [[[0, 0], [0, 0], [0, 0]], [[0, 0], [0, 0], [0, 0]]],
        "decks": [{"main": [0, 3], "side": []}, {"main": [2, 8], "side": []}],
    }


def test_extract_counts_sightings_and_keys_maindeck_to_the_taker():
    rows = extract_event_rows(_compact(), "PEASANT", "evt-1")

    by_name = {row.card_name: row for row in rows}
    assert len(rows) == 12
    assert sum(row.seen_count for row in rows) == 18
    assert all(row.seat is not None and row.pick_num is not None for row in rows)

    wheeled = by_name["c1"]
    assert wheeled.seen_count == 2
    assert wheeled.saw_count == 2
    assert wheeled.last_seen_sum == 3

    assert by_name["c0"].maindecked is True
    assert by_name["c1"].maindecked is False
    assert by_name["c8"].maindecked is False
