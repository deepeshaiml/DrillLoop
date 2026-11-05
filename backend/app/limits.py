from __future__ import annotations

import json


class _BodyLimitExceeded(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject oversized API bodies before multipart parsing or endpoint execution."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                await self._reject(send, 400, "INVALID_CONTENT_LENGTH", "Request size is invalid.")
                return
            if declared_size < 0 or declared_size > self.max_bytes:
                await self._reject(
                    send, 413, "REQUEST_TOO_LARGE", "Request exceeds the 31 MB limit."
                )
                return

        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise _BodyLimitExceeded
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyLimitExceeded:
            await self._reject(send, 413, "REQUEST_TOO_LARGE", "Request exceeds the 31 MB limit.")

    @staticmethod
    async def _reject(send, status: int, code: str, message: str):
        body = json.dumps({"detail": {"code": code, "message": message}}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
