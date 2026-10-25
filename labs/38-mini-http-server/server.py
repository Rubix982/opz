"""A small HTTP/1.1 server on raw sockets. Lab 38: you build the parts marked TODO.

What's given (don't change the behaviour, the harness relies on it):
    Request, HTTPError, Response, render(), app()   -- parsing results, routes, bytes on the wire
    MiniHTTPServer.__init__                         -- binds and listens

What you build:
    read_request()                   -- read ONE request from a socket, however the bytes arrive
    MiniHTTPServer.handle_connection -- serve requests on one connection until it should close
    MiniHTTPServer.serve_forever     -- accept connections, with a bounded number of workers
    MiniHTTPServer.shutdown          -- stop accepting, let in-flight requests finish, return

The contract is in each docstring and in README.md.
"""

import socket
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

REASONS = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    413: "Content Too Large",
    431: "Request Header Fields Too Large",
    500: "Internal Server Error",
    505: "HTTP Version Not Supported",
}


@dataclass
class Request:
    method: str                  # "GET", "POST", ...
    target: str                  # "/echo?x=1"
    version: str                 # "HTTP/1.1" or "HTTP/1.0"
    headers: dict[str, str]      # names lower-cased: {"content-length": "5"}
    body: bytes = b""

    @property
    def path(self) -> str:
        return urlsplit(self.target).path

    @property
    def query(self) -> dict[str, list[str]]:
        return parse_qs(urlsplit(self.target).query)

    def wants_close(self) -> bool:
        """True if the client asked for the connection to close after this request."""
        conn = self.headers.get("connection", "").lower()
        if self.version == "HTTP/1.0":
            return conn != "keep-alive"
        return conn == "close"


class HTTPError(Exception):
    """Raise with a status (400, 408, 413, 431, 505) for a request you must refuse."""

    def __init__(self, status: int, message: str = ""):
        super().__init__(message or REASONS.get(status, ""))
        self.status = status


@dataclass
class Response:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


def render(resp: Response, close: bool) -> bytes:
    """The response as bytes on the wire, always with Content-Length."""
    head = [f"HTTP/1.1 {resp.status} {REASONS.get(resp.status, 'Unknown')}"]
    headers = {"Content-Length": str(len(resp.body)), **resp.headers}
    headers["Connection"] = "close" if close else "keep-alive"
    head += [f"{k}: {v}" for k, v in headers.items()]
    return ("\r\n".join(head) + "\r\n\r\n").encode("latin-1") + resp.body


def app(req: Request) -> Response:
    """The routes.

    GET  /hello          -> 200 "hello\\n"
    POST /echo           -> 200 with the request body
    GET  /sleep?ms=N     -> waits N ms (max 3000), then 200 "slept N\\n"
    known path, wrong method -> 405;  anything else -> 404
    """
    routes = {"/hello": "GET", "/echo": "POST", "/sleep": "GET"}
    if req.path not in routes:
        return Response(404, b"not found\n")
    if req.method != routes[req.path]:
        return Response(405, b"method not allowed\n", {"Allow": routes[req.path]})
    if req.path == "/hello":
        return Response(200, b"hello\n", {"Content-Type": "text/plain"})
    if req.path == "/echo":
        return Response(200, req.body, {"Content-Type": "application/octet-stream"})
    ms = min(int(req.query.get("ms", ["0"])[0] or 0), 3000)
    time.sleep(ms / 1000)
    return Response(200, f"slept {ms}\n".encode())


# ---------------------------------------------------------------- yours


def read_request(
    sock: socket.socket,
    buffer: bytearray,
    *,
    header_timeout: float,
    idle_timeout: float,
    max_header_bytes: int,
    max_body_bytes: int,
) -> Request | None:
    """Read exactly one request from `sock` and return it.

    `buffer` holds bytes already received on this connection but not used yet:
    a client may send several requests in one packet (pipelining), so after you
    take one request off the front, leave the rest in `buffer` for the next call.

    The bytes can arrive in any split: one byte per recv(), the head and body in
    separate packets, or three requests at once. Never assume one recv() is one
    request.

    Returns None if the client closed the connection cleanly before sending any
    byte of a new request (or stayed silent for `idle_timeout` seconds between
    requests).

    Raises HTTPError for a request you must refuse:
        400  malformed request line, header line without ":", bad Content-Length,
             non-ASCII bytes in the request line, EOF mid-request
        408  the head (request line + headers) didn't finish within
             `header_timeout` seconds of its first byte. This is a deadline for
             the WHOLE head, not per recv(): a client sending one byte every
             0.3s must still be cut off.
        413  Content-Length larger than `max_body_bytes` (don't read the body)
        431  the head is longer than `max_header_bytes` before its blank line
        505  a version other than HTTP/1.0 or HTTP/1.1

    Header names are case-insensitive: store them lower-cased.
    """
    raise NotImplementedError


class MiniHTTPServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        max_workers: int = 16,
        header_timeout: float = 2.0,
        idle_timeout: float = 5.0,
        max_header_bytes: int = 8192,
        max_body_bytes: int = 1_000_000,
    ):
        self.max_workers = max_workers
        self.header_timeout = header_timeout
        self.idle_timeout = idle_timeout
        self.max_header_bytes = max_header_bytes
        self.max_body_bytes = max_body_bytes
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(256)
        self.address = self.sock.getsockname()  # (host, port), known right away

    def handle_connection(self, conn: socket.socket) -> None:
        """Serve requests on one connection until it should close, then close it.

        For each request from read_request(): call app(), send render(...).
        Keep the connection open for the next request (keep-alive) unless the
        request wants_close(), the server is shutting down, or something failed.

        On HTTPError: send that status (with a short body) and close.
        If app() raises: send 500 and close. Nothing a client sends may crash
        the server or leak an exception out of this method.
        """
        raise NotImplementedError

    def serve_forever(self) -> None:
        """Accept connections and hand each to handle_connection().

        At most `max_workers` connections are handled at the same time, and the
        server never runs more than about `max_workers` threads however many
        clients connect (no thread per connection). Extra connections wait
        their turn (the kernel's listen backlog, or a queue you keep).

        Returns after shutdown() has been called.
        """
        raise NotImplementedError

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop the server gracefully, from another thread.

        Stop accepting new connections; let requests already being processed
        finish and send their response; close idle keep-alive connections; then
        return (within `timeout` seconds). After it returns, new connections are
        refused.
        """
        raise NotImplementedError


if __name__ == "__main__":
    srv = MiniHTTPServer(port=8038)
    print(f"listening on http://{srv.address[0]}:{srv.address[1]}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
