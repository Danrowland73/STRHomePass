"""A size cap on logo uploads that applies before the body is read.

FastAPI reads a multipart body, file included, into a temporary file before
the route or its dependencies run, so a size check inside the route (or the
admin or API key check) only happens after a large upload has already
arrived. A chunked request has no Content-Length to check at all. This sits in
front of the whole app and counts bytes as they arrive, answering 413 as soon as
the limit is passed. A proxy in front can still set a lower limit.
"""
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def is_logo_upload(scope: Scope) -> bool:
    """POST /admin/tokens/{id}/logo and POST /api/v1/tokens/{id}/logo, with
    or without a proxy prefix in front."""
    path = scope.get("path", "")
    return scope.get("method") == "POST" and "/tokens/" in path and path.endswith("/logo")


class LogoUploadLimit:
    def __init__(self, app: ASGIApp, limit: int, message: str) -> None:
        self.app = app
        self.limit = limit
        self.message = message

    def applies(self, scope: Scope) -> bool:
        return is_logo_upload(scope)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.applies(scope):
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.limit:
            await self._refuse(scope, receive, send)
            return

        seen = 0
        exceeded = False

        async def limited_receive():
            # Past the limit the body is cut off as if the client hung up. The
            # app is not asked to read more, and whatever it answers on the way
            # out (FastAPI turns a failed form read into a 400) is replaced by
            # the 413 below.
            nonlocal seen, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            if not exceeded:
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
        if exceeded:
            await self._refuse(scope, receive, send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"detail": self.message}, status_code=413, headers={"Connection": "close"})
        await response(scope, receive, send)


# Every other request body: guest commands, PIN and claim forms, admin JSON.
# None of them legitimately comes near this (a link with 2,000 entities is about
# 100 KB). Without a cap, FastAPI reads a JSON or form body in full before the
# route runs, so anyone could post an arbitrarily large body to a made-up guest
# link and have it held in memory before the link was even looked up.
REQUEST_BODY_LIMIT = 256 * 1024


class RequestBodyLimit(LogoUploadLimit):
    """The same cut-off as LogoUploadLimit, for every request that is not a logo
    upload (those keep their own, larger, limit)."""

    def applies(self, scope: Scope) -> bool:
        return not is_logo_upload(scope)
