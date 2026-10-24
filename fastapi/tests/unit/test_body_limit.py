import asyncio

import pytest
from starlette.requests import ClientDisconnect

from app.core.body_limit import BodyLimitMiddleware


def test_chunked_body_replay_disconnect_and_passthrough():
    async def scenario():
        received = []

        async def target(scope, receive, send):
            if scope["type"] == "http":
                received.append(await receive())
                received.append(await receive())
            else:
                received.append(scope["type"])

        async def send(message):
            received.append(message)

        messages = iter(
            [
                {"type": "http.request", "body": b"a", "more_body": True},
                {"type": "http.request", "body": b"b"},
                {"type": "http.disconnect"},
            ]
        )

        async def receive():
            return next(messages)

        middleware = BodyLimitMiddleware(target, 64)
        await middleware({"type": "http", "headers": []}, receive, send)
        assert received[0]["body"] == b"ab" and received[1]["type"] == "http.disconnect"
        await middleware({"type": "websocket"}, receive, send)
        assert received[-1] == "websocket"

        async def disconnect():
            return {"type": "http.disconnect"}

        with pytest.raises(ClientDisconnect):
            await middleware({"type": "http", "headers": []}, disconnect, send)

    asyncio.run(scenario())
