"""Run blocking SDK work in daemon threads that cannot hold process exit."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar

T = TypeVar("T")


def _deliver(loop: asyncio.AbstractEventLoop, callback: Callable[[], None]) -> None:
    try:
        loop.call_soon_threadsafe(callback)
    except RuntimeError:
        # The CLI may have finished while an orphaned browser/Gemini call was
        # still winding down. Dropping the delivery is intentional.
        return


async def run_daemon(function: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Await a blocking function in a daemon thread.

    ``asyncio.to_thread`` uses the loop executor, whose non-daemon workers are
    joined during interpreter shutdown. TinyFish agent streams cannot be
    cancelled, so a timed-out agent could otherwise keep the CLI alive for a
    minute after the hunt has already committed and persisted its results.
    """

    loop = asyncio.get_running_loop()
    future: asyncio.Future[T] = loop.create_future()

    def resolve(value: T) -> None:
        if not future.done():
            future.set_result(value)

    def reject(exc: BaseException) -> None:
        if not future.done():
            future.set_exception(exc)

    def worker() -> None:
        try:
            value = function(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - propagated to the awaiting task
            _deliver(loop, partial(reject, exc))
        else:
            _deliver(loop, partial(resolve, value))

    threading.Thread(
        target=worker,
        name=f"unclaimed-daemon-{getattr(function, '__name__', 'call')}",
        daemon=True,
    ).start()
    return await future
