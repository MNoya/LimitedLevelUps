import pytest

from bot.services.transcript_edit import (
    TranscriptEditError,
    merge_transcript_segments,
    relink_changed_segments,
    word_count,
)


def test_merge_preserves_non_editable_fields_and_edits_text():
    stored = [
        {"t": 0, "head_t": 0, "heading": "Intro", "text": "old intro", "cards": [{"name": "Llanowar Elves"}]},
        {"t": 12, "subheading": "Draft 1", "text": "old body", "cards": []},
        {"t": 30, "text": "closing", "cards": []},
    ]
    incoming = [
        {"t": 999, "heading": "Intro", "text": "new intro", "cards": []},
        {"t": 999, "subheading": "Draft 1", "text": "new body"},
        {"t": 999, "text": "closing edited"},
    ]

    merged = merge_transcript_segments(stored, incoming)

    assert [s["t"] for s in merged] == [0, 12, 30]
    assert merged[0]["head_t"] == 0
    assert merged[0]["cards"] == [{"name": "Llanowar Elves"}]
    assert [s["text"] for s in merged] == ["new intro", "new body", "closing edited"]


def test_dropping_subheading_removes_only_that_field():
    stored = [{"t": 5, "subheading": "Aside", "text": "body", "cards": []}]
    incoming = [{"t": 5, "text": "body"}]

    merged = merge_transcript_segments(stored, incoming)

    assert "subheading" not in merged[0]
    assert merged[0]["text"] == "body"
    assert merged[0]["t"] == 5


def test_emptying_heading_removes_it():
    stored = [{"t": 0, "heading": "Old", "text": "body"}]
    incoming = [{"t": 0, "heading": "   ", "text": "body"}]

    merged = merge_transcript_segments(stored, incoming)

    assert "heading" not in merged[0]


def test_empty_paragraph_is_rejected():
    stored = [{"t": 0, "text": "body"}]
    incoming = [{"t": 0, "text": "   "}]

    with pytest.raises(TranscriptEditError):
        merge_transcript_segments(stored, incoming)


def test_segment_count_mismatch_is_rejected():
    stored = [{"t": 0, "text": "a"}, {"t": 1, "text": "b"}]
    incoming = [{"t": 0, "text": "a"}]

    with pytest.raises(TranscriptEditError):
        merge_transcript_segments(stored, incoming)


def test_relink_only_touches_changed_segments():
    stored = [
        {"t": 0, "text": "kept intact", "cards": [{"name": "Old Card"}]},
        {"t": 5, "text": "the shok deals damage"},
    ]
    merged = [
        {"t": 0, "text": "kept intact", "cards": [{"name": "Old Card"}]},
        {"t": 5, "text": "the shok deals damage edited"},
    ]

    def tagger(text):
        return (text.replace("shok", "Shock"), [{"name": "Shock"}])

    relink_changed_segments(stored, merged, tagger)

    assert merged[0]["text"] == "kept intact"
    assert merged[0]["cards"] == [{"name": "Old Card"}]
    assert merged[1]["text"] == "the Shock deals damage edited"
    assert merged[1]["cards"] == [{"name": "Shock"}]


def test_relink_drops_cards_when_changed_segment_has_none():
    stored = [{"t": 0, "text": "had a card", "cards": [{"name": "Gone"}]}]
    merged = [{"t": 0, "text": "no card now", "cards": [{"name": "Gone"}]}]

    relink_changed_segments(stored, merged, lambda text: (text, []))

    assert "cards" not in merged[0]


def test_word_count_matches_pipeline_semantics():
    segments = [{"text": "one two three"}, {"text": ">>Shock>> deals damage"}]

    assert word_count(segments) == 6
