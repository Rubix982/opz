"""Test harness for lab 38. Run through ./check.sh.

Each test starts your server in its own process and attacks it over real
sockets: split-up requests, pipelining, many clients, malformed and oversized
requests, slow clients, idle connections, and a shutdown mid-request. A test
that hangs is killed at its deadline and printed as a FAIL.
"""

import os
import socket
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Fail(Exception):
    pass


# ---------------------------------------------------------------- client side


def start(**config):
    """Start a MiniHTTPServer in a background thread; returns (server, thread)."""
    from server import MiniHTTPServer

    srv = MiniHTTPServer(port=0, **config)
    crashed: list[BaseException] = []

    def run() -> None:
        try:
            srv.serve_forever()
        except BaseException as e:  # surface it in the test, not in a dead thread
            crashed.append(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(0.1)
    if crashed:
        raise crashed[0]
    return srv, t


def connect(srv, timeout: float = 5.0) -> socket.socket:
    s = socket.create_connection(srv.address, timeout=timeout)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return s


class Reader:
    """Reads responses off one client socket, keeping leftover bytes."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""

    def _fill(self) -> bool:
        chunk = self.sock.recv(65536)
        if not chunk:
            return False
        self.buf += chunk
        return True

    def response(self) -> tuple[int, dict[str, str], bytes]:
        while b"\r\n\r\n" not in self.buf:
            if not self._fill():
                raise Fail(f"server closed the connection before a full response (got {self.buf[:60]!r})")
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ", 2)
        if len(parts) < 2 or not parts[0].startswith("HTTP/") or not parts[1].isdigit():
            raise Fail(f"not an HTTP status line: {lines[0]!r}")
        headers = {}
        for line in lines[1:]:
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
        n = int(headers.get("content-length", "0"))
        while len(self.buf) < n:
            if not self._fill():
                raise Fail("server closed the connection in the middle of a response body")
        body, self.buf = self.buf[:n], self.buf[n:]
        return int(parts[1]), headers, body

    def closed_within(self, seconds: float) -> bool:
        """True if the server closes the connection within `seconds` (data before EOF is ignored)."""
        self.sock.settimeout(seconds)
        end = time.monotonic() + seconds
        try:
            while time.monotonic() < end:
                if not self.sock.recv(65536):
                    return True
        except (ConnectionResetError, BrokenPipeError):
            return True
        except socket.timeout:
            return False
        return False


def get(srv, path: str = "/hello", timeout: float = 5.0) -> tuple[int, bytes]:
    with connect(srv, timeout) as s:
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
        status, _, body = Reader(s).response()
        return status, body


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise Fail(msg)


# ---------------------------------------------------------------- tests


def test_basics() -> str:
    srv, _ = start()
    status, body = get(srv, "/hello")
    expect((status, body) == (200, b"hello\n"), f"GET /hello -> {status} {body!r}")
    with connect(srv) as s:
        s.sendall(b"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 11\r\nConnection: close\r\n\r\nhello there")
        status, headers, body = Reader(s).response()
        expect((status, body) == (200, b"hello there"), f"POST /echo -> {status} {body!r}")
        expect(headers.get("content-length") == "11", "response has no correct Content-Length")
    with connect(srv) as s:  # header names are case-insensitive
        s.sendall(b"POST /echo HTTP/1.1\r\nhOsT: x\r\ncontent-LENGTH: 2\r\nConnection: close\r\n\r\nok")
        status, _, body = Reader(s).response()
        expect((status, body) == (200, b"ok"), f"lower/mixed-case Content-Length ignored: {status} {body!r}")
    status, _ = get(srv, "/nope")
    expect(status == 404, f"GET /nope -> {status}, want 404")
    status, _ = get(srv, "/echo")
    expect(status == 405, f"GET /echo -> {status}, want 405")
    return "routes, bodies, case-insensitive headers, 404/405"


def test_partial() -> str:
    srv, _ = start()
    # one byte per packet
    with connect(srv) as s:
        req = b"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\nConnection: close\r\n\r\nabcde"
        for i in range(len(req)):
            s.sendall(req[i : i + 1])
            time.sleep(0.004)
        status, _, body = Reader(s).response()
        expect((status, body) == (200, b"abcde"), f"request sent one byte at a time -> {status} {body!r}")
    # head and body in separate packets, body itself in pieces
    with connect(srv) as s:
        s.sendall(b"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 12\r\nConnection: close\r\n\r\n")
        time.sleep(0.15)
        for piece in (b"twelve", b" by", b"tes"):
            s.sendall(piece)
            time.sleep(0.1)
        status, _, body = Reader(s).response()
        expect((status, body) == (200, b"twelve bytes"), f"body arriving in pieces -> {status} {body!r}")
    # the split lands inside "\r\n\r\n"
    with connect(srv) as s:
        s.sendall(b"GET /hello HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r")
        time.sleep(0.15)
        s.sendall(b"\n")
        status, _, body = Reader(s).response()
        expect(status == 200, f"blank line split across packets -> {status}")
    return "one byte per packet, body in pieces, CRLFCRLF split across packets"


def test_keepalive() -> str:
    srv, _ = start()
    with connect(srv) as s:
        r = Reader(s)
        s.sendall(
            b"GET /hello HTTP/1.1\r\nHost: x\r\n\r\n"
            b"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\n\r\none"
            b"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\n\r\ntwo"
        )
        got = [r.response() for _ in range(3)]
        bodies = [b for _, _, b in got]
        expect(bodies == [b"hello\n", b"one", b"two"], f"3 pipelined requests in one packet -> {bodies}")
        time.sleep(0.3)
        s.sendall(b"GET /hello HTTP/1.1\r\nHost: x\r\n\r\n")
        status, _, _ = r.response()
        expect(status == 200, "a 4th request on the same kept-alive connection failed")
        s.sendall(b"GET /hello HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        status, headers, _ = r.response()
        expect(headers.get("connection", "").lower() == "close", "response to Connection: close doesn't say close")
        expect(r.closed_within(2), "server kept the connection open after Connection: close")
    with connect(srv) as s:
        r = Reader(s)
        s.sendall(b"GET /hello HTTP/1.0\r\n\r\n")
        r.response()
        expect(r.closed_within(2), "HTTP/1.0 without keep-alive: connection not closed")
    return "3 pipelined requests in order, reuse after a pause, close when asked, HTTP/1.0"


def test_concurrent() -> str:
    srv, _ = start(max_workers=16)
    clients, per = 40, 25
    errors: list[str] = []

    def client(i: int) -> None:
        try:
            if i % 2:  # half reuse one connection, half reconnect every time
                with connect(srv, 15) as s:
                    r = Reader(s)
                    for j in range(per):
                        body = f"c{i}-{j}".encode()
                        s.sendall(b"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
                        status, _, got = r.response()
                        if (status, got) != (200, body):
                            errors.append(f"client {i}: sent {body!r}, got {status} {got!r}")
                            return
            else:
                for _ in range(per):
                    status, body = get(srv, "/hello", 15)
                    if status != 200:
                        errors.append(f"client {i}: {status}")
                        return
        except Exception as e:
            errors.append(f"client {i}: {type(e).__name__}: {e}")

    # more concurrent clients than workers: keep-alive clients hold a worker for
    # their whole run, so some have to wait. All must finish.
    threads = [threading.Thread(target=client, args=(i,), daemon=True) for i in range(clients)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(40)
    expect(not any(t.is_alive() for t in threads), "clients still waiting after 40s")
    expect(not errors, f"{len(errors)} clients failed, first: {errors[0] if errors else ''}")
    return f"{clients} clients × {per} requests, all answered correctly in {time.monotonic() - t0:.1f}s"


MALFORMED = [
    # (what, bytes, acceptable statuses)
    ("garbage request line", b"GARBAGE\r\n\r\n", {400}),
    ("no HTTP version", b"GET /hello\r\n\r\n", {400}),
    ("header without a colon", b"GET /hello HTTP/1.1\r\nNoColonHere\r\n\r\n", {400}),
    ("Content-Length: abc", b"POST /echo HTTP/1.1\r\nContent-Length: abc\r\n\r\n", {400}),
    ("Content-Length: -5", b"POST /echo HTTP/1.1\r\nContent-Length: -5\r\n\r\n", {400}),
    ("non-ASCII in the request line", b"GET /h\xffllo HTTP/1.1\r\n\r\n", {400}),
    ("HTTP/9.9", b"GET /hello HTTP/9.9\r\n\r\n", {505, 400}),
    ("9,000 bytes of headers, never finished", b"GET /hello HTTP/1.1\r\nX-Big: " + b"a" * 9000, {431}),
    ("Content-Length: 50,000,000", b"POST /echo HTTP/1.1\r\nContent-Length: 50000000\r\n\r\n", {413}),
]


def test_malformed() -> str:
    srv, thread = start(header_timeout=2.0)
    for what, data, ok in MALFORMED:
        with connect(srv) as s:
            try:
                s.sendall(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            r = Reader(s)
            try:
                status, _, _ = r.response()
            except (Fail, ConnectionResetError, socket.timeout) as e:
                raise Fail(f"{what}: no error response ({type(e).__name__}: {e})")
            expect(status in ok, f"{what}: got {status}, want {sorted(ok)}")
            expect(r.closed_within(2), f"{what}: connection left open after the error")
    # the client gives up halfway: no response needed, but no crash either
    for what, data in [
        ("EOF in the middle of the headers", b"GET /hello HTTP/1.1\r\nHost: x\r\n"),
        ("EOF in the middle of the body", b"POST /echo HTTP/1.1\r\nContent-Length: 10\r\n\r\nabc"),
    ]:
        with connect(srv) as s:
            s.sendall(data)
            s.shutdown(socket.SHUT_WR)
            expect(Reader(s).closed_within(3), f"{what}: server never closed the connection")
    expect(thread.is_alive(), "serve_forever() died")
    status, _ = get(srv)
    expect(status == 200, f"after the bad requests GET /hello -> {status}")
    return f"{len(MALFORMED)} bad requests answered 4xx/5xx and closed; 2 half-requests; still serving"


def test_slowloris() -> str:
    srv, _ = start(max_workers=16, header_timeout=1.5)
    slow = 10
    cut: list[float | None] = [None] * slow
    stop = threading.Event()

    def trickle(i: int) -> None:
        payload = b"GET /hello HTTP/1.1\r\nX-Slow: " + b"z" * 200
        t0 = time.monotonic()
        try:
            with connect(srv) as s:
                s.settimeout(0.3)
                for byte in payload:
                    if stop.is_set():
                        return
                    s.sendall(bytes([byte]))
                    try:
                        if s.recv(4096) == b"":
                            break
                        break  # any reply (a 408) also means it was cut off
                    except socket.timeout:
                        continue
                cut[i] = time.monotonic() - t0
        except (BrokenPipeError, ConnectionResetError):
            cut[i] = time.monotonic() - t0

    threads = [threading.Thread(target=trickle, args=(i,), daemon=True) for i in range(slow)]
    for t in threads:
        t.start()
    time.sleep(0.3)
    worst = 0.0
    for _ in range(10):
        t0 = time.monotonic()
        status, _ = get(srv, "/hello", 3)
        worst = max(worst, time.monotonic() - t0)
        expect(status == 200, f"normal request during the slow clients -> {status}")
    expect(worst < 0.5, f"a normal request took {worst:.2f}s while slow clients were connected")
    end = time.monotonic() + 5
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    stop.set()
    left = sum(c is None for c in cut)
    expect(left == 0, f"{left} of {slow} clients sending a byte every 0.3s were never cut off "
                      "(is the header timeout per recv() instead of for the whole head?)")
    latest = max(c for c in cut if c is not None)
    expect(latest < 1.5 + 1.5, f"slow clients cut off only after {latest:.1f}s (header_timeout is 1.5s)")
    return f"normal requests stayed fast (worst {worst*1000:.0f} ms); {slow} trickling clients cut off by {latest:.1f}s"


def test_bounded() -> str:
    workers = 8
    base = threading.active_count()
    srv, _ = start(max_workers=workers, header_timeout=1.0, idle_timeout=1.0)
    idle = [connect(srv, 20) for _ in range(40)]
    time.sleep(0.4)
    peak = 0
    for _ in range(10):
        peak = max(peak, threading.active_count() - base)
        time.sleep(0.05)
    expect(peak <= workers + 4,
           f"{peak} server threads for 40 idle connections (max_workers={workers}): a thread per connection?")
    t0 = time.monotonic()
    status, _ = get(srv, "/hello", 15)
    waited = time.monotonic() - t0
    expect(status == 200, f"a real request behind 40 idle connections -> {status}")
    expect(waited < 10, f"a real request waited {waited:.1f}s behind idle connections")
    still_open = 0
    for s in idle:
        if not Reader(s).closed_within(8):
            still_open += 1
        s.close()
    expect(still_open == 0, f"{still_open} idle connections never closed by the server (idle_timeout=1s)")
    return f"40 idle connections used at most {peak} threads; real request served in {waited:.1f}s; idle ones closed"


def test_shutdown() -> str:
    srv, thread = start(max_workers=8)
    result: dict = {}

    def slow_request() -> None:
        try:
            result["slow"] = get(srv, "/sleep?ms=800", 10)
        except Exception as e:
            result["slow"] = e

    idle = connect(srv)
    idle.sendall(b"GET /hello HTTP/1.1\r\nHost: x\r\n\r\n")
    idle_reader = Reader(idle)
    idle_reader.response()  # an open keep-alive connection, now idle
    t = threading.Thread(target=slow_request, daemon=True)
    t.start()
    time.sleep(0.2)
    t0 = time.monotonic()
    done = threading.Event()
    threading.Thread(target=lambda: (srv.shutdown(timeout=5), done.set()), daemon=True).start()
    expect(done.wait(6), "shutdown() didn't return within 6s")
    took = time.monotonic() - t0
    t.join(3)
    slow = result.get("slow")
    expect(slow == (200, b"slept 800\n"), f"the request in flight during shutdown -> {slow!r}")
    expect(took < 3.5, f"shutdown() took {took:.1f}s")
    thread.join(3)
    expect(not thread.is_alive(), "serve_forever() didn't return after shutdown()")
    expect(idle_reader.closed_within(3), "an idle keep-alive connection was left open after shutdown")
    try:
        status, _ = get(srv, "/hello", 2)
        raise Fail(f"a new connection after shutdown was still served ({status})")
    except (ConnectionRefusedError, ConnectionResetError, BrokenPipeError, socket.timeout, OSError, Fail) as e:
        if isinstance(e, Fail) and "still served" in str(e):
            raise
    return f"in-flight request finished, idle connection closed, returned in {took:.1f}s, new connections refused"


TESTS = {
    "basics": (test_basics, 15),
    "partial-reads": (test_partial, 20),
    "keep-alive": (test_keepalive, 15),
    "concurrent": (test_concurrent, 50),
    "malformed": (test_malformed, 40),
    "slowloris": (test_slowloris, 25),
    "bounded-threads": (test_bounded, 40),
    "shutdown": (test_shutdown, 20),
}


def run_one(name: str) -> int:
    fn, _ = TESTS[name]
    try:
        print(fn())
        return 0
    except NotImplementedError:
        print("not implemented yet")
    except Fail as e:
        print(e)
    except Exception:
        print("crashed: " + traceback.format_exc(limit=3).strip().splitlines()[-1])
    return 1


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--one":
        sys.stdout.flush()
        code = run_one(sys.argv[2])
        sys.stdout.flush()
        os._exit(code)  # don't wait for stuck threads
    only = sys.argv[1:]
    failed = 0
    for name, (_, deadline) in TESTS.items():
        if only and name not in only:
            continue
        try:
            r = subprocess.run([sys.executable, __file__, "--one", name],
                               capture_output=True, text=True, timeout=deadline)
            msg = (r.stdout.strip() or r.stderr.strip() or "no output").splitlines()
            ok = r.returncode == 0
            detail = msg[0] if ok else "\n        ".join(msg[:6])
        except subprocess.TimeoutExpired:
            ok, detail = False, f"hung for {deadline}s"
        print(f"{'pass' if ok else 'FAIL'}  {name:16} {detail}")
        failed += not ok
    print("LAB PASSED" if not failed else "lab not passed yet")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
