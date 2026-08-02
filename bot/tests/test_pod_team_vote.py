from bot.services.pod_team_vote import (
    TEAM_VOTE_LOCKED_TITLE,
    TEAM_VOTE_TEAM_COLUMN,
    TEAM_VOTE_WAIT_COLUMN,
    TEAM_VOTE_SETTINGS_HINT,
    build_team_vote_locked_embed,
    build_team_vote_offer_embed,
    build_team_vote_waited_embed,
    needed_from_embed,
    rerender_gathering,
    team_vote_needed,
    team_voters_from_embed,
    wait_voters_from_embed,
)


def test_team_vote_needed_is_a_majority_of_the_pod():
    assert team_vote_needed(4) == 3
    assert team_vote_needed(6) == 4
    assert team_vote_needed(8) == 5
    assert team_vote_needed(10) == 6


def test_offer_embed_states_the_target_and_shows_both_columns_empty():
    embed = build_team_vote_offer_embed([], [], pod_size=6)

    assert needed_from_embed(embed) == 4
    assert TEAM_VOTE_TEAM_COLUMN in embed.fields[0].name
    assert TEAM_VOTE_WAIT_COLUMN in embed.fields[1].name
    assert "(0)" not in embed.fields[0].name
    assert embed.fields[0].value == "-"
    assert embed.fields[1].value == "-"


def test_columns_carry_their_own_voters():
    embed = build_team_vote_offer_embed(["<@111>", "<@222>"], ["<@333>"], pod_size=6)

    assert team_voters_from_embed(embed) == ["<@111>", "<@222>"]
    assert wait_voters_from_embed(embed) == ["<@333>"]
    assert embed.fields[0].name.startswith("🤝 Team Draft (2)")


def test_voter_read_dedupes_and_normalizes_nickname_mentions():
    embed = build_team_vote_offer_embed(["<@!111>", "<@111>", "<@222>"], [], pod_size=6)

    assert team_voters_from_embed(embed) == ["<@111>", "<@222>"]


def test_locked_card_flips_title_keeps_columns_and_notes_settings():
    locked = build_team_vote_locked_embed(["<@111>", "<@222>"], ["<@333>"])

    assert locked.title == TEAM_VOTE_LOCKED_TITLE
    assert locked.description == TEAM_VOTE_SETTINGS_HINT
    assert team_voters_from_embed(locked) == ["<@111>", "<@222>"]
    assert wait_voters_from_embed(locked) == ["<@333>"]


def test_waited_card_notes_settings_and_keeps_the_record():
    waited = build_team_vote_waited_embed(["<@111>"], ["<@222>", "<@333>"])

    assert waited.description == TEAM_VOTE_SETTINGS_HINT
    assert wait_voters_from_embed(waited) == ["<@222>", "<@333>"]


def test_rerender_preserves_title_and_target_while_swapping_columns():
    original = build_team_vote_offer_embed(["<@111>"], [], pod_size=6)

    updated = rerender_gathering(original, ["<@111>", "<@222>"], ["<@333>"])

    assert updated.title == original.title
    assert needed_from_embed(updated) == 4
    assert team_voters_from_embed(updated) == ["<@111>", "<@222>"]
    assert wait_voters_from_embed(updated) == ["<@333>"]
