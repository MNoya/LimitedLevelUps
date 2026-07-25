from bot.services.pod_swiss import Standing
from bot.services.pod_tournament import (
    build_champion_embed,
    normalize_player_name,
)


def test_medals_hidden_while_champion_undecided():
    embed = build_champion_embed(
        _standings(), pending_count=1, champion_locked=False,
    )
    assert "Arcyl" in embed.description
    for medal in ("🥇", "🥈", "🥉"):
        assert medal not in embed.description


def test_champion_medal_shown_once_locked_even_with_matches_pending():
    embed = build_champion_embed(
        _standings(), pending_count=1, champion_locked=True,
    )
    assert "1. 🥇 Arcyl" in embed.description  # 3-0 champion is uncatchable, medal shows now
    assert "🥈" not in embed.description  # runner-up medals wait for all results
    assert "🥉" not in embed.description


def test_medals_shown_once_standings_final():
    embed = build_champion_embed(_standings(), pending_count=0)
    assert "1. 🥇 Arcyl" in embed.description
    assert "2. 🥈 Elfandor" in embed.description
    assert "3. 🥉 Bramblewick" in embed.description


def test_draft_log_link_points_at_in_site_reviewer_keyed_on_slug():
    key = normalize_player_name("Arcyl")
    embed = build_champion_embed(
        _standings(),
        event_name="SOS Early Pod Draft 4",
        displays={key: {"display_name": "Arcyl", "slug": "arcyl"}},
        event_has_log=True, )

    assert "/pods/sos-early-pod-draft-4/arcyl" in embed.description
    assert "magicprotools.com" not in embed.description


def test_draft_log_link_omitted_without_slug():
    key = normalize_player_name("Arcyl")
    embed = build_champion_embed(
        _standings(),
        event_name="SOS Early Pod Draft 4",
        displays={key: {"display_name": "Arcyl", "slug": None}},
        event_has_log=True, )

    assert "Draft Log" not in embed.description


def test_draft_log_link_omitted_without_event_log():
    key = normalize_player_name("Arcyl")
    embed = build_champion_embed(
        _standings(),
        event_name="SOS Early Pod Draft 4",
        displays={key: {"display_name": "Arcyl", "slug": "arcyl"}},
        event_has_log=False, )

    assert "Draft Log" not in embed.description


def _standing(rank: int, name: str, wins: int, losses: int) -> Standing:
    return Standing(
        rank=rank, player_id=f"p{rank}", player_name=name,
        wins=wins, losses=losses, omw_pct=0.5, gw_pct=0.5, ogw_pct=0.5,
    )


def _standings() -> list[Standing]:
    return [
        _standing(1, "Arcyl", 3, 0),
        _standing(2, "Elfandor", 2, 1),
        _standing(3, "Bramblewick", 2, 1),
    ]
