from starlette.requests import ClientDisconnect

from app.core.errors import response


class BodyLimitMiddleware:
    """Bound the receive stream before Starlette buffers/parses it, even without Content-Length."""

    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self.limit() if callable(self.limit) else self.limit
        length = dict(scope["headers"]).get(b"content-length", b"0")
        try:
            too_large = int(length) > limit
        except ValueError:
            too_large = False
        body = bytearray()
        if not too_large:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    raise ClientDisconnect()
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > limit:
                    too_large = True
                    break
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
        if too_large:
            return await response(413, "REQUEST_TOO_LARGE", "Request body exceeds limit")(
                scope, receive, send
            )
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
