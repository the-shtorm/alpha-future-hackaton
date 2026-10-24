import asyncio
import threading

import pytest

from app.core.errors import ServiceError
from app.schemas.requests import RankRequest
from app.services.ranker import Ranker
from app.services.runner import RankRunner


def test_bounded_jobs_serialization_and_cancellation(payload, encoder, settings):
    async def scenario():
        started, release = threading.Event(), threading.Event()
        original = encoder.encode
        active, maximum = [0], [0]

        def slow(texts):
            active[0] += 1
            maximum[0] = max(maximum[0], active[0])
            started.set()
            assert release.wait(5)
            result = original(texts)
            active[0] -= 1
            return result

        encoder.encode = slow
        runner = RankRunner(Ranker(encoder), settings)
        request = RankRequest.model_validate(payload)
        jobs = [asyncio.create_task(runner.run(request)) for _ in range(4)]
        assert await asyncio.to_thread(started.wait, 2)
        try:
            jobs[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await jobs[0]
            with pytest.raises(ServiceError) as busy:
                await runner.run(request)
            assert busy.value.code == "SERVICE_BUSY"
            assert runner.slots.locked()  # Cancelled client has not released its encode job.
        finally:
            release.set()
            await asyncio.gather(*jobs, return_exceptions=True)
            await runner.close()
        assert maximum[0] == 1
        with pytest.raises(ServiceError) as error:
            await runner.run(request)
        assert error.value.code == "MODEL_NOT_READY"

    asyncio.run(scenario())


def test_admission_empty_duplicates_and_executor_failure(payload, encoder, settings):
    async def scenario():
        runner = RankRunner(Ranker(encoder), settings)
        request = RankRequest.model_validate(payload)
        request.candidates.append(request.candidates[0])
        with pytest.raises(ServiceError, match="unique"):
            await runner.run(request)
        request.candidates = []
        assert (await runner.run(request)).results == []
        request = RankRequest.model_validate(payload)
        runner.executor.shutdown()
        with pytest.raises(RuntimeError):
            await runner.run(request)
        assert runner.slots._value == 4
        await runner.close()

    asyncio.run(scenario())
