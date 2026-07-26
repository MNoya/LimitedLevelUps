from datetime import date

import requests
from sqlalchemy import select

from bot.models import DraftEvent, MagicSet, Player, PlayerStats
from bot.services import refresh as refresh_mod
from bot.services.refresh import (
    TRANSIENT_COOLDOWN_S,
    TRANSIENT_MAX_RETRIES,
    bulk_upsert_draft_events,
    claim_orphan_drafts,
    rebuild_player_stats,
    refresh_active_players,
    refresh_active_players_all_sets,
    refresh_one_player_for_all_sets,
    refresh_player,
)
from bot.sets import active_set_code


class FakeClient:
    def __init__(self, drafts=None, raise_=None):
        self.drafts = drafts or []
        self.raise_ = raise_
        self.calls: list[tuple[str, object, object]] = []

    def fetch_drafts(self, token, start_date=None, end_date=None):
        self.calls.append((token, start_date, end_date))
        if self.raise_ is not None:
            raise self.raise_
        return list(self.drafts)


class ExplodingClient:
    def fetch_drafts(self, token, start_date=None, end_date=None):  # pragma: no cover
        raise AssertionError("client should not be called for skipped player")


def _make_404():
    resp = requests.Response()
    resp.status_code = 404
    return requests.HTTPError(response=resp)


def _make_500():
    resp = requests.Response()
    resp.status_code = 500
    return requests.HTTPError(response=resp)


def _make_403():
    resp = requests.Response()
    resp.status_code = 403
    return requests.HTTPError(response=resp)


class TransientThenOkClient:
    def __init__(self, fail_times, drafts=None):
        self.fail_times = fail_times
        self.drafts = drafts or []
        self.calls = 0

    def fetch_drafts(self, token, start_date=None, end_date=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise _make_403()
        return list(self.drafts)


def _seed_set(session, code="ECL", start_date=date(2026, 1, 20)):
    s = MagicSet(code=code, name=code, start_date=start_date)
    session.add(s)
    session.flush()
    return s


def _seed_active_set(session):
    return _seed_set(session, code=active_set_code(), start_date=date(2026, 4, 21))


def _seed_player(session, name="P", token_suffix="a", active=True, token_invalid=False):
    token = (token_suffix * 32)[:32]
    p = Player(
        slug=f"{name.lower()}-{token_suffix}",
        discord_id=f"refresh-{name.lower()}-{token_suffix}",
        display_name=name,
        seventeenlands_token=token,
        active=active,
        token_invalid=token_invalid,
    )
    session.add(p)
    session.flush()
    return p


def _draft(event_id, **overrides):
    base = {
        "id": event_id,
        "format": "PremierDraft",
        "expansion": "SOS",
        "wins": 5,
        "losses": 3,
        "event_wins": 0,
        "colors": "WB",
        "start_rank": "Gold-3",
        "end_rank": "Platinum-4",
        "first_event_server_time": "2026-04-28 23:16:43",
        "last_event_server_time": "2026-04-28 23:39:04",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# bulk_upsert_draft_events
# ---------------------------------------------------------------------------


def test_bulk_upsert_routes_to_matching_set(session):
    sos = _seed_set(session, code="SOS")
    p = _seed_player(session)
    result = bulk_upsert_draft_events(session, p.id, [_draft("a", expansion="SOS")], [sos])
    session.flush()

    rows = session.execute(select(DraftEvent).where(DraftEvent.player_id == p.id)).scalars().all()
    assert [r.set_id for r in rows] == [sos.id]
    assert result["touched_pairs"] == {(p.id, sos.id)}
    assert result["unrouted_expansions"] == {}


def test_bulk_upsert_alchemy_variant_routes_to_parent_set(session):
    """Y26ECL substring-matches ECL → ECL set, raw expansion preserved on the row."""
    ecl = _seed_set(session, code="ECL")
    p = _seed_player(session)
    bulk_upsert_draft_events(session, p.id, [_draft("a", expansion="Y26ECL")], [ecl])
    session.flush()

    [row] = session.execute(select(DraftEvent).where(DraftEvent.player_id == p.id)).scalars().all()
    assert row.set_id == ecl.id
    assert row.expansion == "Y26ECL"


def test_bulk_upsert_unrouted_expansion_leaves_set_id_null(session):
    """A draft in an un-registered expansion still persists, with set_id=NULL."""
    ecl = _seed_set(session, code="ECL")
    p = _seed_player(session)
    result = bulk_upsert_draft_events(session, p.id, [_draft("a", expansion="MYSTERY")], [ecl])
    session.flush()

    [row] = session.execute(select(DraftEvent).where(DraftEvent.player_id == p.id)).scalars().all()
    assert row.set_id is None
    assert row.expansion == "MYSTERY"
    assert result["unrouted_expansions"] == {"MYSTERY": 1}
    assert result["touched_pairs"] == set()


def test_bulk_upsert_keeps_unknown_formats_and_tallies_them(session):
    """Unknown format strings are persisted (not dropped); reported in unknown_formats."""
    sos = _seed_set(session, code="SOS")
    p = _seed_player(session)
    result = bulk_upsert_draft_events(
        session, p.id, [_draft("a", format="MysteryCubeDraft")], [sos]
    )
    session.flush()

    [row] = session.execute(select(DraftEvent).where(DraftEvent.player_id == p.id)).scalars().all()
    assert row.format == "MysteryCubeDraft"
    assert row.set_id == sos.id
    assert result["unknown_formats"] == {"MysteryCubeDraft": 1}


def test_bulk_upsert_treats_midweek_as_known_not_unknown(session):
    """MidWeek* are casual events: persisted but never reported as unknown formats."""
    sos = _seed_set(session, code="SOS")
    p = _seed_player(session)
    result = bulk_upsert_draft_events(
        session, p.id, [_draft("a", format="MidWeekSealed"), _draft("b", format="MidWeekQuickDraft")], [sos]
    )
    session.flush()

    stored = {r.format for r in session.execute(select(DraftEvent).where(DraftEvent.player_id == p.id)).scalars()}
    assert stored == {"MidWeekSealed", "MidWeekQuickDraft"}
    assert result["unknown_formats"] == {}


def test_bulk_upsert_is_idempotent(session):
    """Re-running with the same drafts must not duplicate rows."""
    sos = _seed_set(session, code="SOS")
    p = _seed_player(session)
    drafts = [_draft("a"), _draft("b")]
    bulk_upsert_draft_events(session, p.id, drafts, [sos])
    session.flush()
    bulk_upsert_draft_events(session, p.id, drafts, [sos])
    session.flush()
    rows = session.execute(select(DraftEvent).where(DraftEvent.player_id == p.id)).scalars().all()
    assert len(rows) == 2


def test_bulk_upsert_updates_changed_fields_on_repull(session):
    """When 17lands amends an event (e.g. wins went from 2 to 7), the row updates."""
    sos = _seed_set(session, code="SOS")
    p = _seed_player(session)
    bulk_upsert_draft_events(session, p.id, [_draft("a", wins=2, colors="WB")], [sos])
    session.flush()
    bulk_upsert_draft_events(session, p.id, [_draft("a", wins=7, colors="WBg", event_wins=7)], [sos])
    session.flush()
    [row] = session.execute(select(DraftEvent).where(DraftEvent.player_id == p.id)).scalars().all()
    assert row.wins == 7
    assert row.colors == "WBg"
    assert row.is_trophy is True


def test_bulk_upsert_isolates_per_player(session):
    """Same 17lands event_id under different players must not collide."""
    sos = _seed_set(session, code="SOS")
    p1 = _seed_player(session, name="P1", token_suffix="a")
    p2 = _seed_player(session, name="P2", token_suffix="b")
    bulk_upsert_draft_events(session, p1.id, [_draft("shared", wins=7)], [sos])
    bulk_upsert_draft_events(session, p2.id, [_draft("shared", wins=2)], [sos])
    session.flush()
    by_player = {
        r.player_id: r
        for r in session.execute(select(DraftEvent)).scalars().all()
    }
    assert by_player[p1.id].wins == 7
    assert by_player[p2.id].wins == 2


# ---------------------------------------------------------------------------
# rebuild_player_stats
# ---------------------------------------------------------------------------


def test_rebuild_player_stats_aggregates_by_format_and_expansion(session):
    """Two formats + two expansions = four rows. Counts/sums match the underlying events."""
    sos = _seed_set(session, code="SOS")
    p = _seed_player(session)
    session.flush()
    drafts = [
        _draft("a", format="PremierDraft", expansion="SOS", wins=5, losses=3),
        _draft("b", format="PremierDraft", expansion="SOS", wins=7, losses=0, event_wins=7),
        _draft("c", format="PremierDraft", expansion="Y26SOS", wins=4, losses=3),
        _draft("d", format="TradDraft", expansion="SOS", wins=4, losses=0, event_wins=4),
    ]
    bulk_upsert_draft_events(session, p.id, drafts, [sos])
    session.flush()
    rebuild_player_stats(session, p.id, sos.id)

    rows = session.execute(select(PlayerStats).where(PlayerStats.player_id == p.id)).scalars().all()
    by_key = {(r.format, r.expansion): r for r in rows}
    assert set(by_key) == {
        ("PremierDraft", "SOS"),
        ("PremierDraft", "Y26SOS"),
        ("TradDraft", "SOS"),
    }
    assert by_key[("PremierDraft", "SOS")].events == 2
    assert by_key[("PremierDraft", "SOS")].wins == 12
    assert by_key[("PremierDraft", "SOS")].trophies == 1
    assert by_key[("TradDraft", "SOS")].trophies == 1


def test_rebuild_player_stats_wipes_stale_rows(session):
    """A row that no longer has matching draft_events is removed."""
    sos = _seed_set(session, code="SOS")
    p = _seed_player(session)
    session.add(PlayerStats(
        player_id=p.id, set_id=sos.id, format="StaleFormat", expansion="SOS",
        events=99, wins=99, losses=0, games_played=99, trophies=9,
    ))
    session.flush()
    rebuild_player_stats(session, p.id, sos.id)
    rows = session.execute(select(PlayerStats).where(PlayerStats.player_id == p.id)).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# claim_orphan_drafts
# ---------------------------------------------------------------------------


def test_claim_orphan_drafts_attaches_matching_unrouted_events(session):
    """An orphan event with expansion containing the new set's code gets claimed."""
    ecl = _seed_set(session, code="ECL")
    p = _seed_player(session)
    bulk_upsert_draft_events(session, p.id, [_draft("a", expansion="MYS")], [ecl])
    session.flush()
    [orphan] = session.execute(select(DraftEvent)).scalars().all()
    assert orphan.set_id is None

    mys = _seed_set(session, code="MYS", start_date=date(2026, 7, 1))
    affected = claim_orphan_drafts(session, mys)

    [claimed] = session.execute(select(DraftEvent)).scalars().all()
    assert claimed.set_id == mys.id
    assert affected == {p.id}


def test_claim_orphan_drafts_leaves_non_matching_orphans_alone(session):
    """Adding set FOO does not claim orphans whose expansion is BAR."""
    ecl = _seed_set(session, code="ECL")
    p = _seed_player(session)
    bulk_upsert_draft_events(session, p.id, [_draft("a", expansion="BAR")], [ecl])
    session.flush()

    foo = _seed_set(session, code="FOO", start_date=date(2026, 7, 1))
    affected = claim_orphan_drafts(session, foo)
    assert affected == set()
    [row] = session.execute(select(DraftEvent)).scalars().all()
    assert row.set_id is None


def test_claim_orphan_drafts_normalizes_legacy_alias_rows(session):
    """A row ingested before its alias existed (raw alias string, no code match) is normalized and claimed."""
    ecl = _seed_set(session, code="ECL")
    p = _seed_player(session)
    bulk_upsert_draft_events(session, p.id, [_draft("a", expansion="RAWALIAS")], [ecl])
    session.flush()

    canon = _seed_set(session, code="CANON", start_date=date(2026, 7, 1))
    affected = claim_orphan_drafts(session, canon, expansion_alias="RAWALIAS")

    [row] = session.execute(select(DraftEvent)).scalars().all()
    assert row.set_id == canon.id
    assert row.expansion == "CANON"
    assert affected == {p.id}


def test_claim_orphan_drafts_keeps_matched_expansions_verbatim(session):
    """``expansion_matches`` rows join the set without losing their 17lands name, which is what keeps
    the cube variants separable on their own boards."""
    ecl = _seed_set(session, code="ECL")
    p = _seed_player(session)
    drafts = [_draft("a", expansion="Cube - Planar"), _draft("b", expansion="Cube")]
    bulk_upsert_draft_events(session, p.id, drafts, [ecl])
    session.flush()

    cube = _seed_set(session, code="CUBE", start_date=date(2026, 7, 1))
    affected = claim_orphan_drafts(session, cube, expansion_matches=("Cube - Planar", "Cube"))

    rows = session.execute(select(DraftEvent)).scalars().all()
    assert {row.set_id for row in rows} == {cube.id}
    assert {row.expansion for row in rows} == {"Cube - Planar", "Cube"}
    assert affected == {p.id}


# ---------------------------------------------------------------------------
# refresh_player
# ---------------------------------------------------------------------------


def test_refresh_player_writes_stats_and_events(session):
    _seed_set(session, code="ECL")
    p = _seed_player(session)
    drafts = [
        _draft("alpha", format="PremierDraft", expansion="ECL", wins=5, losses=3),
        _draft("beta", format="TradDraft", expansion="ECL", wins=4, losses=0, event_wins=4),
    ]
    client = FakeClient(drafts=drafts)
    result = refresh_player(session, client, p)
    session.flush()

    assert result["status"] == "updated"
    assert result["events"] == 2
    stats = session.execute(select(PlayerStats).where(PlayerStats.player_id == p.id)).scalars().all()
    by_fmt = {r.format: r for r in stats}
    assert by_fmt["PremierDraft"].wins == 5
    assert by_fmt["TradDraft"].trophies == 1
    events = session.execute(select(DraftEvent).where(DraftEvent.player_id == p.id)).scalars().all()
    assert sorted(e.seventeenlands_event_id for e in events) == ["alpha", "beta"]


def test_refresh_player_404_invalidates_token(session):
    _seed_set(session, code="ECL")
    p = _seed_player(session)
    result = refresh_player(session, FakeClient(raise_=_make_404()), p)
    assert result == {"status": "invalidated"}
    assert p.token_invalid is True


def test_refresh_player_5xx_does_not_invalidate(session):
    _seed_set(session, code="ECL")
    p = _seed_player(session)
    result = refresh_player(session, FakeClient(raise_=_make_500()), p)
    assert result["status"] == "error"
    assert p.token_invalid is False


def test_refresh_player_malformed_response_does_not_invalidate(session):
    """Signup verifies tokens, so a malformed 200 is a 17lands bug — don't blame the user."""
    _seed_set(session, code="ECL")
    p = _seed_player(session)
    result = refresh_player(session, FakeClient(raise_=ValueError("bad json")), p)
    assert result["status"] == "error"
    assert p.token_invalid is False


def test_refresh_player_network_error_does_not_invalidate(session):
    _seed_set(session, code="ECL")
    p = _seed_player(session)
    result = refresh_player(session, FakeClient(raise_=requests.ConnectTimeout("timeout")), p)
    assert result["status"] == "error"
    assert p.token_invalid is False


def test_refresh_player_403_returns_transient(session):
    _seed_set(session, code="ECL")
    p = _seed_player(session)

    result = refresh_player(session, FakeClient(raise_=_make_403()), p)

    assert result["status"] == "transient"
    assert p.token_invalid is False


def test_refresh_player_connection_drop_returns_transient(session):
    _seed_set(session, code="ECL")
    p = _seed_player(session)

    dropped = requests.ConnectionError("('Connection aborted.', RemoteDisconnected())")
    result = refresh_player(session, FakeClient(raise_=dropped), p)

    assert result["status"] == "transient"
    assert p.token_invalid is False


def test_transient_retry_pauses_then_succeeds(session, monkeypatch):
    _seed_active_set(session)
    p = _seed_player(session)
    sleeps = []
    monkeypatch.setattr(refresh_mod._time, "sleep", lambda s: sleeps.append(s))
    client = TransientThenOkClient(fail_times=1)

    result = refresh_mod._refresh_player_retrying_transient(
        session, client, p, date(2026, 4, 21), idx=1, n_total=1
    )

    assert result["status"] == "updated"
    assert sleeps == [TRANSIENT_COOLDOWN_S]
    assert client.calls == 2


def test_transient_retry_gives_up_after_max_retries(session, monkeypatch):
    _seed_active_set(session)
    p = _seed_player(session)
    sleeps = []
    monkeypatch.setattr(refresh_mod._time, "sleep", lambda s: sleeps.append(s))
    client = TransientThenOkClient(fail_times=99)

    result = refresh_mod._refresh_player_retrying_transient(
        session, client, p, date(2026, 4, 21), idx=5, n_total=10
    )

    assert result["status"] == "error"
    assert len(sleeps) == TRANSIENT_MAX_RETRIES
    assert client.calls == TRANSIENT_MAX_RETRIES + 1


# ---------------------------------------------------------------------------
# refresh_active_players
# ---------------------------------------------------------------------------


def test_refresh_active_players_skips_inactive_and_token_invalid(session):
    _seed_active_set(session)
    active_ok = _seed_player(session, name="ok", token_suffix="a")
    _seed_player(session, name="inactive", token_suffix="b", active=False)
    _seed_player(session, name="invalid", token_suffix="c", token_invalid=True)
    session.flush()

    client = FakeClient(drafts=[_draft("x", expansion=active_set_code(), event_wins=7)])
    summary = refresh_active_players(session, client)

    assert summary["updated"] == 1
    assert summary["invalidated"] == 0
    assert summary["errors"] == 0
    assert [c[0] for c in client.calls] == [active_ok.seventeenlands_token]


def test_refresh_active_players_skips_pod_only_players_without_token(session):
    _seed_active_set(session)
    active_ok = _seed_player(session, name="ok", token_suffix="a")
    pod_only = Player(
        slug="pod-only",
        discord_id="refresh-pod-only",
        display_name="pod-only",
        seventeenlands_token=None,
        active=True,
        leaderboard_opt_in=False,
    )
    session.add(pod_only)
    session.flush()

    client = FakeClient(drafts=[_draft("x", expansion=active_set_code(), event_wins=7)])
    summary = refresh_active_players(session, client)

    assert summary["invalidated"] == 0
    assert [c[0] for c in client.calls] == [active_ok.seventeenlands_token]
    session.refresh(pod_only)
    assert pod_only.token_invalid is False


def test_refresh_active_players_summary_counts_mixed_statuses(session):
    _seed_active_set(session)
    _seed_player(session, name="ok", token_suffix="a")
    p_404 = _seed_player(session, name="bad", token_suffix="b")
    p_5xx = _seed_player(session, name="flaky", token_suffix="c")
    session.flush()

    err_404 = _make_404()
    err_500 = _make_500()

    class RoutingClient:
        def __init__(self):
            self.calls = []

        def fetch_drafts(self, token, start_date=None, end_date=None):
            self.calls.append(token)
            if token == p_404.seventeenlands_token:
                raise err_404
            if token == p_5xx.seventeenlands_token:
                raise err_500
            return [_draft("x", expansion=active_set_code())]

    summary = refresh_active_players(session, RoutingClient())
    assert summary["updated"] == 1
    assert summary["invalidated"] == 1
    assert summary["errors"] == 1
    assert summary["invalidated_players"] == [p_404.id]


def test_refresh_active_players_no_active_set(session):
    _seed_set(session, code="OLD")
    _seed_player(session)
    session.flush()
    summary = refresh_active_players(session, ExplodingClient())
    assert summary["status"] == "no_active_set"


def test_refresh_active_players_all_sets_uses_earliest_set_start(session):
    """Console-only path: fetch_start is the earliest registered set."""
    _seed_set(session, code="A", start_date=date(2025, 6, 9))
    _seed_set(session, code="B", start_date=date(2026, 1, 20))
    _seed_player(session)
    session.flush()
    client = FakeClient(drafts=[])
    refresh_active_players_all_sets(session, client)
    assert client.calls and client.calls[0][1] == date(2025, 6, 9)


def test_refresh_one_player_unknown_id_returns_no_player(session):
    _seed_set(session, code="SOS")
    result = refresh_one_player_for_all_sets(session, FakeClient(), "nonexistent-id")
    assert result == {"status": "no_player"}


def test_refresh_one_player_no_sets_returns_no_sets(session):
    p = _seed_player(session)
    session.commit()
    result = refresh_one_player_for_all_sets(session, FakeClient(), p.id)
    assert result == {"status": "no_sets"}
