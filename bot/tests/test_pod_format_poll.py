from datetime import datetime, timezone

from bot.services import pod_format_poll as poll


def _mentions(*ids: str) -> list[str]:
    return [f"<@{i}>" for i in ids]


def test_votes_read_back_off_the_card():
    options = ["MSH", "NEO", "IKO"]
    votes = {"MSH": ["<@1>", "<@2>"], "NEO": ["<@3>"], "IKO": []}

    embed = poll.build_format_poll_embed(options, votes)
    read = poll.votes_from_embed(embed)

    assert read["MSH"] == ["<@1>", "<@2>"]
    assert read["NEO"] == ["<@3>"]
    assert read["IKO"] == []
    assert poll.options_from_embed(embed) == options


def test_write_in_credit_reads_back_off_the_card():
    options = ["MSH", "NEO"]
    votes = {"MSH": [], "NEO": ["<@3>"]}
    adders = {"NEO": "Wren"}

    embed = poll.build_format_poll_embed(options, votes, adders=adders)
    read_adders = poll.adders_from_embed(embed)
    read_votes = poll.votes_from_embed(embed)

    assert read_adders == {"NEO": "Wren"}
    assert read_votes["NEO"] == ["<@3>"]


def test_credit_survives_rerender():
    options = ["MSH", "NEO"]
    adders = {"NEO": "Wren"}
    embed = poll.build_format_poll_embed(options, {"NEO": ["<@3>"]}, adders=adders)

    rerendered = poll.rerender_gathering(embed, options, {"NEO": ["<@3>", "<@4>"]}, poll.adders_from_embed(embed))

    assert poll.adders_from_embed(rerendered) == {"NEO": "Wren"}


def test_option_name_shows_bracketed_code_then_name_without_repeating_code():
    embed = poll.build_format_poll_embed(["MSH"], {"MSH": []})
    name = embed.fields[0].name

    assert "[MSH]" in name
    assert "Marvel Super Heroes" in name
    assert "(MSH)" not in name


def test_toggle_vote_is_multiple_choice():
    options = ["MSH", "NEO", "IKO"]
    votes: dict[str, list[str]] = {}

    poll.toggle_vote(votes, options, "<@1>", "NEO")
    poll.toggle_vote(votes, options, "<@1>", "IKO")

    assert votes["NEO"] == ["<@1>"]
    assert votes["IKO"] == ["<@1>"]


def test_toggle_vote_retracts_on_repeat_click():
    options = ["MSH", "NEO"]
    votes: dict[str, list[str]] = {}

    poll.toggle_vote(votes, options, "<@1>", "NEO")
    poll.toggle_vote(votes, options, "<@1>", "NEO")

    assert votes["NEO"] == []


def test_normalize_write_in_accepts_plausible_codes_only():
    assert poll.normalize_write_in("neo") == "NEO"
    assert poll.normalize_write_in("  mh3 ") == "MH3"
    assert poll.normalize_write_in("Y26ECL") == "Y26ECL"
    assert poll.normalize_write_in("") is None
    assert poll.normalize_write_in("a") is None
    assert poll.normalize_write_in("not a code") is None


def test_normalize_write_ins_splits_on_spaces_and_commas():
    assert poll.normalize_write_ins("DSK FIN MH3") == ["DSK", "FIN", "MH3"]
    assert poll.normalize_write_ins("msh, tmt , dsk") == ["MSH", "TMT", "DSK"]
    assert poll.normalize_write_ins("NEO NEO neo") == ["NEO"]
    assert poll.normalize_write_ins("  ") == []
    assert poll.normalize_write_ins("FIN not-a-code MH3") == ["FIN", "MH3"]


def test_build_options_opens_with_only_latest_and_the_flashback_signal():
    when = datetime(2026, 7, 20, tzinfo=timezone.utc)

    options = poll.build_options(when)

    assert options == [poll.active_set_code(when), poll.ANY_FLASHBACK_CODE]


def test_order_options_floats_the_best_voted_set_below_latest_and_the_signal():
    options = ["MSH", poll.ANY_FLASHBACK_CODE, "KHM", "FIN", "NEO"]
    votes = {"KHM": _mentions("1"), "FIN": _mentions("2", "3", "4"), "NEO": _mentions("5", "6")}

    ordered = poll.order_options(options, votes)

    assert ordered == ["MSH", poll.ANY_FLASHBACK_CODE, "FIN", "NEO", "KHM"]


def test_order_options_keeps_card_order_on_a_vote_tie():
    options = ["MSH", poll.ANY_FLASHBACK_CODE, "KHM", "FIN"]
    votes = {"KHM": _mentions("1"), "FIN": _mentions("2")}

    ordered = poll.order_options(options, votes)

    assert ordered == ["MSH", poll.ANY_FLASHBACK_CODE, "KHM", "FIN"]


def test_button_layout_puts_latest_and_flashback_in_top_row_and_rest_below():
    options = ["MSH", poll.ANY_FLASHBACK_CODE, "FIN", "NEO"]

    layout = poll.format_poll_button_layout(options)

    top_row = [(code, label) for code, label, row in layout if row == 0]
    assert (options[0], poll.LATEST_BUTTON_LABEL) in top_row
    assert (poll.ANY_FLASHBACK_CODE, None) in top_row
    assert all(row >= 1 for code, label, row in layout if code not in (options[0], poll.ANY_FLASHBACK_CODE))
