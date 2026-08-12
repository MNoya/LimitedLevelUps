from datetime import datetime

from bot.scoring import (
    DEFAULT_QUEUE_GROUPS, QueueGroup, boxes_for_event, compute_score, compute_score_breakdown,
    supported_formats,
)


def points_for(label: str) -> int:
    """Group weight straight from scoring_buckets.json, so a weight change doesn't rewrite tests
    whose subject is which formats land in which group."""
    for group in DEFAULT_QUEUE_GROUPS:
        if group.label == label:
            return group.points
    raise AssertionError(f"no queue group labelled {label}")


def test_boxes_2024_six_win_play_sets_pay_two_at_trophy():
    for code in ("OTJ", "FDN", "BLB", "DSK"):
        assert boxes_for_event(code, 6, datetime(2024, 11, 23), is_trophy=True) == 2
        assert boxes_for_event(code, 5, datetime(2024, 11, 23), is_trophy=False) == 0


def test_boxes_aetherdrift_premiere_pays_one_at_trophy():
    assert boxes_for_event("DFT", 6, datetime(2025, 2, 22), is_trophy=True) == 1
    assert boxes_for_event("DFT", 5, datetime(2025, 2, 22), is_trophy=False) == 0


def test_boxes_tdm_collector_premiere_was_six_win():
    premiere = datetime(2025, 4, 19)  # 6-win ladder, so a 6-win trophy pays 1 box
    assert boxes_for_event("TDM", 6, premiere, is_trophy=True) == 1
    assert boxes_for_event("TDM", 5, premiere, is_trophy=False) == 0
    later = datetime(2025, 5, 10)  # after the mid-set 7-win rollout → standard play ladder
    assert boxes_for_event("TDM", 7, later, is_trophy=True) == 2
    assert boxes_for_event("TDM", 6, later, is_trophy=False) == 1


def test_boxes_collector_weekend_pays_one_for_the_win():
    inside = datetime(2026, 4, 30)  # SOS collector premiere (7-win era)
    assert boxes_for_event("SOS", 7, inside, is_trophy=True) == 1
    assert boxes_for_event("SOS", 6, inside, is_trophy=False) == 0


def test_boxes_default_play_booster_ladder_for_later_weekends():
    later = datetime(2026, 5, 20)  # SOS, past the collector window
    assert boxes_for_event("SOS", 7, later, is_trophy=True) == 2
    assert boxes_for_event("SOS", 6, later, is_trophy=False) == 1
    assert boxes_for_event("SOS", 5, later, is_trophy=False) == 0


def test_boxes_tla_collector_weekend_then_play_ladder():
    inside = datetime(2025, 11, 29)  # TLA collector premiere
    assert boxes_for_event("TLA", 7, inside, is_trophy=True) == 1
    assert boxes_for_event("TLA", 6, inside, is_trophy=False) == 0
    later = datetime(2025, 12, 15)  # past the TLA window → standard play ladder
    assert boxes_for_event("TLA", 7, later, is_trophy=True) == 2
    assert boxes_for_event("TLA", 6, later, is_trophy=False) == 1


def test_boxes_collector_window_one_day_slack():
    assert boxes_for_event("SOS", 7, datetime(2026, 4, 29), is_trophy=True) == 1  # day before
    assert boxes_for_event("SOS", 7, datetime(2026, 5, 5), is_trophy=True) == 1   # day after
    assert boxes_for_event("SOS", 7, datetime(2026, 5, 6), is_trophy=True) == 2   # two days out


def test_supported_formats_includes_all_bucket_formats():
    fmts = supported_formats()
    assert "PremierDraft" in fmts
    assert "TradDraft" in fmts
    assert "Sealed" in fmts
    assert "TradSealed" in fmts
    # LCQ slots dormant but accepted as soon as 17lands ships data
    assert "LimitedChampionshipQualifier_Draft1" in fmts
    assert "LimitedChampionshipQualifier_Draft2" in fmts


def test_compute_score_zero_when_no_trophies():
    rows = [
        {"format": "PremierDraft", "events": 5, "wins": 12, "losses": 18, "trophies": 0},
    ]
    assert compute_score(rows) == 0.0


def test_compute_score_legacy_formula_single_bucket():
    # Premier bucket, points=10. trophies=4, events=10 → trophy_rate=0.4
    # shrinkage = 4/(4+2) ≈ 0.6667
    # score = 4 × 10 × 0.4 × 0.6667 = 10.667
    rows = [
        {"format": "PremierDraft", "events": 10, "wins": 50, "losses": 30, "trophies": 4},
    ]
    score = compute_score(rows)
    assert score == round(4 * 10 * 0.4 * (4 / 6), 2)


def test_compute_score_combines_sealed_with_tradsealed():
    # Both go into Sealed group. Combined trophies=3, events=6 → trophy_rate=0.5, shrinkage 3/5
    rows = [
        {"format": "Sealed", "events": 4, "wins": 10, "losses": 8, "trophies": 1},
        {"format": "TradSealed", "events": 2, "wins": 8, "losses": 0, "trophies": 2},
    ]
    score = compute_score(rows)
    assert score == round(3 * points_for("Sealed") * 0.5 * (3 / 5), 2)


def test_weighted_trophies_scale_the_numerator_but_not_the_rate():
    """Rank weight has to move the multiplier only. Same 2 trophies in 8 events either way, so a
    weighted row differs from an unweighted one by exactly the weight ratio."""
    unweighted = [{"format": "PremierDraft", "events": 8, "wins": 40, "losses": 20, "trophies": 2}]
    weighted = [dict(unweighted[0], weighted_trophies=2.6)]

    assert compute_score(weighted) == round(compute_score(unweighted) * (2.6 / 2), 2)


def test_weighted_trophies_aggregate_across_one_group():
    """PremierDraft and ContenderDraft are one queue, so their weighted counts add before scoring."""
    rows = [
        {"format": "PremierDraft", "events": 5, "wins": 25, "losses": 10, "trophies": 2,
         "weighted_trophies": 2.6},
        {"format": "ContenderDraft", "events": 5, "wins": 20, "losses": 12, "trophies": 1,
         "weighted_trophies": 1.5},
    ]
    trophies = 3
    expected_raw = 4.1 * points_for("Premier") * (trophies / 10)

    assert compute_score(rows) == round(expected_raw * (trophies / (trophies + 2)), 2)


def test_rows_without_weighted_trophies_score_unweighted():
    """The column is populated by the stats rebuild, so any other writer must not zero the score."""
    rows = [{"format": "PremierDraft", "events": 4, "wins": 20, "losses": 8, "trophies": 2}]

    assert compute_score(rows) == round(2 * points_for("Premier") * (2 / 4) * (2 / 4), 2)


def test_compute_score_sums_across_groups():
    rows = [
        {"format": "PremierDraft", "events": 10, "wins": 50, "losses": 30, "trophies": 4},
        {"format": "Sealed", "events": 6, "wins": 18, "losses": 8, "trophies": 3},
    ]
    premier_raw = 4 * points_for("Premier") * (4 / 10)
    sealed_raw = 3 * points_for("Sealed") * (3 / 6)
    total_trophies = 4 + 3
    aggregate_confidence = total_trophies / (total_trophies + 2)
    assert compute_score(rows) == round((premier_raw + sealed_raw) * aggregate_confidence, 2)


def test_aggregate_confidence_beats_sum_of_per_group():
    rows = [
        {"format": "PremierDraft", "events": 1, "wins": 7, "losses": 0, "trophies": 1},
        {"format": "QuickDraft", "events": 1, "wins": 7, "losses": 0, "trophies": 1},
    ]
    premier_raw = 1 * 10 * 1
    quick_raw = 1 * 4 * 1
    aggregate_confidence = 2 / (2 + 2)
    per_group_confidence = 1 / (1 + 2)
    aggregate = round((premier_raw + quick_raw) * aggregate_confidence, 2)
    summed_per_group = round(premier_raw * per_group_confidence + quick_raw * per_group_confidence, 2)
    assert compute_score(rows) == aggregate
    assert aggregate > summed_per_group


def test_single_group_unchanged_by_aggregation():
    rows = [{"format": "PremierDraft", "events": 5, "wins": 30, "losses": 10, "trophies": 2}]
    trophies = 2
    raw = trophies * 10 * (trophies / 5)
    confidence = trophies / (trophies + 2)
    assert compute_score(rows) == round(raw * confidence, 2)


def test_compute_score_ignores_unknown_formats():
    rows = [
        {"format": "MidWeekSealed", "events": 5, "wins": 20, "losses": 10, "trophies": 2},
    ]
    assert compute_score(rows) == 0.0


def test_compute_score_includes_qualifier_sealed_variants():
    """Qualifier Weekend and Play-In Trad Sealed map to the Sealed group."""
    rows = [
        {"format": "Qualifier_D1_Sealed", "events": 1, "wins": 7, "losses": 1, "trophies": 1},
    ]
    assert compute_score(rows) == round(1 * points_for("Sealed") * 1 * (1 / 3), 2)


def test_compute_score_lcq_draft_2_special_rule():
    # rule="lcq_draft_2": wins × winrate × points (no trophies, no shrinkage)
    # wins=5, losses=2 → games=7, winrate=5/7
    # score = 5 × (5/7) × 10
    rows = [
        {"format": "LimitedChampionshipQualifier_Draft2",
         "events": 2, "wins": 5, "losses": 2, "trophies": 0},
    ]
    score = compute_score(rows)
    assert score == round(5 * (5 / 7) * 10, 2)


def test_compute_score_handles_zero_events_safely():
    rows = [
        {"format": "PremierDraft", "events": 0, "wins": 0, "losses": 0, "trophies": 0},
    ]
    assert compute_score(rows) == 0.0


def test_compute_score_custom_groups_override():
    custom = (
        QueueGroup("Premier", points=20, formats=("PremierDraft",)),
    )
    rows = [
        {"format": "PremierDraft", "events": 10, "wins": 50, "losses": 30, "trophies": 4},
    ]
    score = compute_score(rows, groups=custom)
    assert score == round(4 * 20 * 0.4 * (4 / 6), 2)


def test_compute_score_breakdown_returns_per_group():
    rows = [
        {"format": "PremierDraft", "events": 10, "wins": 50, "losses": 30, "trophies": 4},
        {"format": "Sealed", "events": 4, "wins": 10, "losses": 8, "trophies": 1},
        {"format": "TradSealed", "events": 2, "wins": 8, "losses": 0, "trophies": 2},
    ]
    breakdown = compute_score_breakdown(rows)
    by_label = {b["label"]: b for b in breakdown}

    assert "Premier" in by_label
    assert by_label["Premier"]["events"] == 10
    assert by_label["Premier"]["trophies"] == 4
    premier_raw = 4 * 10 * (4 / 10)
    total_trophies = 4 + 3
    aggregate_confidence = total_trophies / (total_trophies + 2)
    assert by_label["Premier"]["score"] == round(premier_raw * aggregate_confidence, 2)

    assert "Sealed" in by_label
    sealed_and_trad_sealed_trophies = 1 + 2
    assert by_label["Sealed"]["events"] == 6
    assert by_label["Sealed"]["trophies"] == sealed_and_trad_sealed_trophies
    assert by_label["Sealed"]["wins"] == 18

    parts_total = round(sum(b["score"] for b in breakdown), 2)
    rounding_drift = round(abs(parts_total - compute_score(rows)), 2)
    assert rounding_drift <= 0.01

    groups_with_no_rows_are_skipped = "Trad" not in by_label and "Quick" not in by_label
    assert groups_with_no_rows_are_skipped


def test_compute_score_breakdown_empty():
    assert compute_score_breakdown([]) == []


def test_compute_score_breakdown_skips_unknown_formats():
    rows = [
        {"format": "MidWeekSealed", "events": 5, "wins": 20, "losses": 10, "trophies": 2},
    ]
    assert compute_score_breakdown(rows) == []
