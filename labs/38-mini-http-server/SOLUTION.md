# Lab 38 · Solution (spoilers)

## The three ideas

1. **A buffer per connection.** TCP delivers bytes, not requests. Read into a
   buffer until it holds `\r\n\r\n`, take one request off the front (head plus
   exactly `Content-Length` body bytes), and leave the rest for the next call.
   That one change handles packets split anywhere *and* pipelining.
2. **Deadlines, not timeouts.** `settimeout()` limits a single `recv()`. A
   Slowloris client sends a byte just before each timeout fires and holds the
   connection forever. Compute the deadline for the whole head once, and give
   each `recv()` only the time remaining. Check the size limit inside the read
   loop, so a client can't make you buffer a gigabyte.
3. **A fixed pool.** `max_workers` threads take connections from a queue. The
   accept loop never starts a thread. Under a flood, extra connections wait in
   the queue (and the kernel backlog) instead of exhausting memory.

## Reference implementation

Add `import queue` at the top, and these lines to the end of `__init__`:

```python
        self._lock = threading.Lock()
        self._conns: set[socket.socket] = set()   # every open connection
        self._busy: set[socket.socket] = set()    # connections with a request in progress
        self._stopping = threading.Event()
        self._stopped = threading.Event()
```

Then:

```python
def read_request(
    sock: socket.socket,
    buffer: bytearray,
    *,
    header_timeout: float,
    idle_timeout: float,
    max_header_bytes: int,
    max_body_bytes: int,
) -> Request | None:
    """Read exactly one request from `sock` (see README.md for the contract)."""
    # 1. Between requests: wait up to idle_timeout for the first byte.
    if not buffer:
        sock.settimeout(idle_timeout)
        try:
            chunk = sock.recv(65536)
        except OSError:  # timeout, reset, or closed by shutdown()
            return None
        if not chunk:
            return None
        buffer += chunk

    # 2. The head: one deadline for all of it, measured from its first byte.
    deadline = time.monotonic() + header_timeout
    while (end := buffer.find(b"\r\n\r\n")) == -1:
        if len(buffer) > max_header_bytes:
            raise HTTPError(431)
        _recv_into(sock, buffer, deadline)
    if end > max_header_bytes:
        raise HTTPError(431)
    head = bytes(buffer[:end])
    del buffer[: end + 4]

    # 3. Parse it.
    lines = head.split(b"\r\n")
    try:
        request_line = lines[0].decode("ascii")
    except UnicodeDecodeError:
        raise HTTPError(400, "non-ASCII request line")
    parts = request_line.split(" ")
    if len(parts) != 3 or not parts[0].isalpha() or not parts[1].startswith("/"):
        raise HTTPError(400, "bad request line")
    method, target, version = parts
    if not version.startswith("HTTP/"):
        raise HTTPError(400, "bad version")
    if version not in ("HTTP/1.0", "HTTP/1.1"):
        raise HTTPError(505)
    headers: dict[str, str] = {}
    for raw in lines[1:]:
        name, sep, value = raw.decode("latin-1").partition(":")
        if not sep or not name or name != name.strip():
            raise HTTPError(400, "bad header line")
        headers[name.lower()] = value.strip()

    # 4. The body: exactly Content-Length bytes, no more.
    length = headers.get("content-length", "0")
    if not length.isdigit():
        raise HTTPError(400, "bad Content-Length")
    n = int(length)
    if n > max_body_bytes:
        raise HTTPError(413)
    deadline = time.monotonic() + max(header_timeout, idle_timeout)
    while len(buffer) < n:
        _recv_into(sock, buffer, deadline)
    body = bytes(buffer[:n])
    del buffer[:n]  # anything after it is the next (pipelined) request
    return Request(method, target, version, headers, body)


def _recv_into(sock: socket.socket, buffer: bytearray, deadline: float) -> None:
    """One recv() that respects an absolute deadline. EOF mid-request is a 400."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HTTPError(408)
    sock.settimeout(remaining)
    try:
        chunk = sock.recv(65536)
    except TimeoutError:
        raise HTTPError(408)
    if not chunk:
        raise HTTPError(400, "connection closed mid-request")
    buffer += chunk


class MiniHTTPServer:
    ...  # __init__ as given, plus the lines above

    def handle_connection(self, conn: socket.socket) -> None:
        """Serve requests on one connection until it should close, then close it."""
        buffer = bytearray()
        with self._lock:
            self._conns.add(conn)
        try:
            while not self._stopping.is_set():
                try:
                    req = read_request(
                        conn,
                        buffer,
                        header_timeout=self.header_timeout,
                        idle_timeout=self.idle_timeout,
                        max_header_bytes=self.max_header_bytes,
                        max_body_bytes=self.max_body_bytes,
                    )
                except HTTPError as e:
                    body = f"{e.status} {REASONS.get(e.status, '')}\n".encode()
                    conn.sendall(render(Response(e.status, body), close=True))
                    return
                if req is None:
                    return
                with self._lock:
                    self._busy.add(conn)
                try:
                    try:
                        resp = app(req)
                    except Exception:
                        resp = Response(500, b"internal error\n")
                    close = req.wants_close() or resp.status == 500 or self._stopping.is_set()
                    conn.sendall(render(resp, close))
                finally:
                    with self._lock:
                        self._busy.discard(conn)
                if close:
                    return
        except OSError:
            return  # the client went away; nothing to answer
        finally:
            with self._lock:
                self._conns.discard(conn)
            _close_gently(conn)

    def serve_forever(self) -> None:
        """Accept connections; a fixed pool of max_workers threads serves them."""
        self._queue: queue.Queue[socket.socket | None] = queue.Queue()
        workers = [threading.Thread(target=self._work, daemon=True) for _ in range(self.max_workers)]
        for w in workers:
            w.start()
        self.sock.settimeout(0.2)  # wake up regularly to notice shutdown()
        while not self._stopping.is_set():
            try:
                conn, _ = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._queue.put(conn)
        self.sock.close()  # from here on, new connections are refused
        for _ in workers:
            self._queue.put(None)
        for w in workers:
            w.join()
        self._stopped.set()

    def _work(self) -> None:
        while (conn := self._queue.get()) is not None:
            if self._stopping.is_set():
                _close_gently(conn)  # accepted, but never started: just close
            else:
                self.handle_connection(conn)

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop accepting, let in-flight requests finish, close idle connections."""
        self._stopping.set()
        with self._lock:
            idle = [c for c in self._conns if c not in self._busy]
        for c in idle:
            try:
                c.shutdown(socket.SHUT_RDWR)  # wakes the worker blocked in recv()
            except OSError:
                pass
        self._stopped.wait(timeout)


def _close_gently(conn: socket.socket) -> None:
    """Close after the response has left: FIN first, then drain briefly.

    Closing a socket with unread bytes in it makes the kernel send RST, which can
    destroy the response we just sent before the client reads it.
    """
    try:
        conn.shutdown(socket.SHUT_WR)
        conn.settimeout(0.2)
        while conn.recv(65536):
            pass
    except OSError:
        pass
    finally:
        conn.close()
```

## Details worth knowing

- **Why `_close_gently`.** If you `close()` a socket that still has unread bytes
  from the client (a 431 sent before the oversized header has finished arriving),
  the kernel answers with RST instead of FIN, and the client may discard your
  response before reading it. Shutting down the write side first, then draining
  for a moment, lets the response arrive. Real servers call this "lingering close".
- **The idle connection race.** `shutdown()` closes connections that aren't busy.
  A request that arrives at that exact moment loses its connection. Production
  servers accept this: the client retries, and a well-behaved load balancer has
  already stopped sending (see lab 07's preStop note).
- **The pool still has a limit.** 8 workers held by 40 idle connections means a
  real request waits until idle ones time out (about 5s in the test). Real servers
  avoid this with an event loop (`selectors`, `asyncio`, epoll), where an idle
  connection costs a few KB of memory and no thread. Then the limit is the number
  of file descriptors, and you cap connections per client IP instead.
- **Limits come in pairs.** Every limit here (header size, body size, header
  time, idle time, workers) closes one way to exhaust a resource: memory,
  threads, or time. Real servers have the same list: nginx's
  `client_header_timeout`, `large_client_header_buffers`, `client_max_body_size`,
  `keepalive_timeout` and `worker_connections`.

## What this doesn't cover

- `Transfer-Encoding: chunked` request bodies. A real server must support or
  reject them, and must never accept both `Content-Length` and chunked: that
  disagreement is the root of HTTP request smuggling.
- Header folding, duplicate headers (two `Content-Length`s must be a 400), `Expect: 100-continue`.
- TLS, HTTP/2, and connection limits per client IP.
