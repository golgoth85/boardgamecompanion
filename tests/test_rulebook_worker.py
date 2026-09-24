from __future__ import annotations

import asyncio
import threading

import boardgamecompanion.main as main_module
from boardgamecompanion.settings import settings


def test_worker_shutdown_waits_for_inflight_thread(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingService:
        def run_due(self, *, limit: int) -> None:
            assert limit == 1
            started.set()
            assert release.wait(5)

    service = BlockingService()
    monkeypatch.setattr(
        main_module,
        "get_rulebook_update_service",
        lambda: service,
    )
    monkeypatch.setattr(settings, "rulebook_update_poll_seconds", 0.01)
    monkeypatch.setattr(settings, "rulebook_update_batch_size", 1)

    async def scenario() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(main_module._rulebook_update_worker(stop))

        assert await asyncio.to_thread(started.wait, 2)
        stop.set()
        await asyncio.sleep(0.05)

        assert task.done() is False
        release.set()
        await asyncio.wait_for(task, timeout=2)
        assert task.done() is True

    asyncio.run(scenario())