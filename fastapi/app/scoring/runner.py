"""Dedicated bounded single-thread scoring queue; cancellation retains capacity."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.core.errors import ServiceError


class ScoringRunner:
    def __init__(self, scorer, capacity=4, timeout=1.0):
        self.scorer = scorer
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scoring")
        self.slots = asyncio.Semaphore(capacity)
        self.timeout = timeout
        self.closed = False
        self.capacity = capacity
        self.inflight = 0
        self.completed = 0
        self.failed = 0
        self.busy = 0

    async def run(self, request):
        if self.closed:
            raise ServiceError(503, "MODEL_NOT_READY", "Scoring model is not ready")
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=self.timeout)
        except TimeoutError:
            self.busy += 1
            raise ServiceError(503, "SERVICE_BUSY", "Scoring capacity exhausted") from None
        loop = asyncio.get_running_loop()
        self.inflight += 1
        try:
            future = self.executor.submit(self.scorer.evaluate, request)
        except BaseException:
            self.inflight -= 1
            self.slots.release()
            raise
        future.add_done_callback(lambda result: loop.call_soon_threadsafe(self._complete, result))
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)
        return await asyncio.shield(wrapped)

    def _complete(self, future):
        self.inflight -= 1
        self.completed += 1
        self.failed += int(future.exception() is not None)
        self.slots.release()

    def status(self):
        return {
            "inferenceThreads": 1,
            "maxInflightRequests": self.capacity,
            "inflightRequests": self.inflight,
            "completedRequests": self.completed,
            "failedRequests": self.failed,
            "busyRequests": self.busy,
        }

    async def close(self):
        self.closed = True
        await asyncio.to_thread(self.executor.shutdown, wait=True)
