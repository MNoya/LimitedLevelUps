import contextlib

import bot.services.pod_link_dm as link_dm
from bot.services.pod_link_dm import build_link_dm


def _button_urls(view):
    return [c.url for c in view.children if getattr(c, "url", None)]


def _button_custom_ids(view):
    return [c.custom_id for c in view.children if getattr(c, "custom_id", None)]


def _has_prefix(custom_ids, prefix):
    return any(cid.startswith(f"{prefix}:") for cid in custom_ids)


def test_build_link_dm_linked_personalizes_url_in_body():
    body, view = build_link_dm(
        session_id="LLU-MSH-1", thread_ref="<#1>", arena_name="Tarmo#1", rsvp="yes",
    )

    assert "userName=Tarmo%231" in body
    assert view is None


def test_build_link_dm_unlinked_omits_link_and_offers_link_arena_button():
    body, view = build_link_dm(
        session_id="LLU-MSH-1", thread_ref="<#1>", arena_name=None, rsvp="maybe",
    )

    assert "draftmancer" not in body.lower()
    assert not _button_urls(view)
    assert _has_prefix(_button_custom_ids(view), link_dm.LINK_ARENA_PREFIX)


def test_build_link_dm_rsvp_branch_differs():
    yes, _ = build_link_dm(session_id="S", thread_ref="<#1>", arena_name="A#1", rsvp="yes")
    maybe, _ = build_link_dm(session_id="S", thread_ref="<#1>", arena_name="A#1", rsvp="maybe")

    assert yes != maybe


def test_relink_content_reduces_unlinked_body_to_linked_body():
    args = dict(session_id="S", thread_ref="<#1>", rsvp="maybe")
    linked, _ = build_link_dm(arena_name="A#1", **args)
    unlinked, _ = build_link_dm(arena_name=None, **args)

    assert link_dm._relink_content(unlinked, "S", "A#1") == linked


def test_resolve_recipients_drops_optouts_dedups_and_attaches_handle(monkeypatch):
    prefs = {"1": True, "2": False, "3": True}
    handles = {"1": "Ann#1", "3": None}

    @contextlib.contextmanager
    def fake_session():
        yield None

    monkeypatch.setattr(link_dm, "SessionLocal", fake_session)
    monkeypatch.setattr(link_dm, "dm_draft_link_enabled", lambda s, did: prefs.get(did, True))
    monkeypatch.setattr(link_dm, "player_arena_handle", lambda s, did: handles.get(did))

    recipients = [("1", "Ann", "yes"), ("2", "Bob", "yes"), ("3", "Cy", "maybe"), ("1", "Ann", "maybe")]
    result = link_dm._resolve_recipients(recipients)

    assert result == [("1", "Ann#1", "yes"), ("3", None, "maybe")]
