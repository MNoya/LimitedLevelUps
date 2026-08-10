import asyncio

import pytest

from bot.discord_helpers import RenderQueue


DELAY = 0.02
SETTLE = DELAY * 4


@pytest.mark.parametrize("presses, gap, most", [
    (14, 0.0, 2),
    (14, DELAY / 4, 6),
    (2, DELAY * 3, 2),
])
def test_a_burst_collapses_into_fewer_renders(presses, gap, most):
    renders = []

    async def burst():
        queue = RenderQueue(DELAY)
        for _ in range(presses):
            queue.request("pod", lambda: _record(renders))
            if gap:
                await asyncio.sleep(gap)
        await asyncio.sleep(SETTLE)

    asyncio.run(burst())

    assert 1 <= len(renders) <= most


def test_the_last_request_always_renders():
    """The one that must never break: a collapsed burst still ends on a render, so a card cannot be left
    showing a roster older than the press that asked for it."""
    seen = []

    async def burst_then_one_more() -> int:
        queue = RenderQueue(DELAY)
        for _ in range(5):
            queue.request("pod", lambda: _record(seen))
        await asyncio.sleep(SETTLE)
        settled = len(seen)
        queue.request("pod", lambda: _record(seen))
        await asyncio.sleep(SETTLE)
        return settled

    before = asyncio.run(burst_then_one_more())

    assert len(seen) == before + 1


def test_each_key_renders_on_its_own():
    rendered = []

    async def three_pods():
        queue = RenderQueue(DELAY)
        for key in ("a", "b", "c"):
            for _ in range(4):
                queue.request(key, lambda k=key: _record(rendered, k))
        await asyncio.sleep(SETTLE)

    asyncio.run(three_pods())

    assert sorted(set(rendered)) == ["a", "b", "c"]


def test_a_render_that_raises_leaves_the_key_working():
    """A Discord 500 on one repaint must not wedge that pod's card for the rest of the process."""
    attempts = []

    async def fail_twice():
        queue = RenderQueue(DELAY)
        queue.request("pod", lambda: _explode(attempts))
        await asyncio.sleep(SETTLE)
        queue.request("pod", lambda: _explode(attempts))
        await asyncio.sleep(SETTLE)

    asyncio.run(fail_twice())

    assert len(attempts) == 2


async def _record(sink: list, value=1) -> None:
    sink.append(value)


async def _explode(sink: list) -> None:
    sink.append(1)
    raise RuntimeError("discord said no")
