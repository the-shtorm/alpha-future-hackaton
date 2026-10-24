import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.core.errors import ServiceError


class RankRunner:
    """At most N submitted jobs, one inference thread. Cancellation keeps the active slot."""

    def __init__(self, ranker, settings):
        self.ranker = ranker
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        self.slots = asyncio.Semaphore(settings.max_inflight_rank_requests)
        self.timeout = settings.admission_timeout_seconds
        self.closed = False

    async def run(self, request):
        if self.closed:
            raise ServiceError(503, "MODEL_NOT_READY", "Model is not ready")
        ids = [c.product.id for c in request.candidates]
        if len(set(ids)) != len(ids):
            raise ServiceError(422, "DUPLICATE_PRODUCT_ID", "Product identifiers must be unique")
        if not ids:
            return self.ranker.rank(request)
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=self.timeout)
        except TimeoutError:
            raise ServiceError(503, "SERVICE_BUSY", "Ranking capacity exhausted") from None
        loop = asyncio.get_running_loop()
        try:
            future = self.executor.submit(self.ranker.rank, request)
        except BaseException:
            self.slots.release()
            raise
        future.add_done_callback(lambda _: loop.call_soon_threadsafe(self.slots.release))
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        return await asyncio.shield(wrapped)

    async def close(self):
        self.closed = True
        await asyncio.to_thread(self.executor.shutdown, wait=True)
