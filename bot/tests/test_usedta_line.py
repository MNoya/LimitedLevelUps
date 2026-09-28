import pytest

from bot.listeners.usedta import calls_a_worst_card_ever, says_the_line

CASES = [
    ("they don't make em like they used ta", True),
    ("they ain't makin 'em like they used ta", True),
    ("wizards doesn't print cards like they used to", True),
    ("they used to make good cards", False),
    ("they don't make me feel like they used to", False),
    ("i don't like the cards they make", False),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_line_detection(text, expected):
    assert says_the_line(text) is expected


WORST_CARD_CASES = [
    ("Is this the worst card they've EVER printed?", True),
    ("worst card in the set", False),
]


@pytest.mark.parametrize("text,expected", WORST_CARD_CASES)
def test_worst_card_ever_detection(text, expected):
    assert calls_a_worst_card_ever(text) is expected
