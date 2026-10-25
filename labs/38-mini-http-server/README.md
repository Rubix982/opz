# Lab 38 · Build a Mini HTTP Server

**Time:** ~2 hours · **Needs:** Python 3 (standard library only) · **Cost:** free, all local
**Kind:** `[build]`: nothing is broken yet. You build it, and the harness tries to break it.

## The scenario

An internal service runs on a home-grown HTTP server: a thread per connection,
`data = conn.recv(4096)`, split on `\r\n`, answer. It passed every test. In
production:

- Requests that arrived in two TCP packets were rejected as garbage.
- A burst of clients created thousands of threads, and the box ran out of memory.
- One client that opened a connection and sent a byte every few seconds held a
  worker forever (Slowloris). A hundred such clients took the service down
  without sending any real traffic.
- A malformed header crashed the handler thread, and a huge one ate memory.

You'll build the server properly, on raw sockets, with no `http.server`.

## What to build

Everything marked `raise NotImplementedError` in `server.py`. The request and
response types, the routes (`app()`) and `render()` are given.

1. **`read_request(sock, buffer, ...)`**: read exactly one request, however
   the bytes arrive. Leave any extra bytes in `buffer`: they're the next request.
2. **`handle_connection(conn)`**: requests in a loop (keep-alive), the right
   error status for bad ones, and nothing a client sends may crash the server.
3. **`serve_forever()`**: accept connections, served by at most `max_workers`
   threads.
4. **`shutdown()`**: stop accepting, let in-flight requests finish, close idle
   connections, return.

| Situation | Answer |
|---|---|
| malformed request line, header line without `:`, bad `Content-Length`, non-ASCII request line | `400` and close |
| head not finished within `header_timeout` of its first byte | `408` and close |
| `Content-Length` over `max_body_bytes` | `413` and close, without reading the body |
| head longer than `max_header_bytes` | `431` and close |
| version other than HTTP/1.0 or 1.1 | `505` and close |
| `app()` raises | `500` and close |
| silent for `idle_timeout` between requests | just close |

Try it by hand: `python3 server.py`, then `curl -v localhost:8038/hello` or
`printf 'GET /hello HTTP/1.1\r\n\r\n' | nc localhost 8038`.

## Run the harness

```bash
./check.sh              # everything (about a minute)
./check.sh slowloris    # one test
```

| Test | What it does to your server |
|---|---|
| basics | the routes, an echoed body, mixed-case header names, 404 and 405 |
| partial-reads | a request sent one byte per packet; a body in three pieces; `\r\n\r\n` split across two packets |
| keep-alive | three requests in a single packet (pipelining), reuse after a pause, `Connection: close`, HTTP/1.0 |
| concurrent | 40 clients × 25 requests, more clients than workers |
| malformed | nine bad requests, each needing the right 4xx/5xx and a closed connection; two clients that hang up mid-request; then a normal request must still work |
| slowloris | 10 clients each sending one byte every 0.3s; normal requests must stay fast, and the slow ones must be cut off soon after `header_timeout` |
| bounded-threads | 40 idle connections with `max_workers=8`: the thread count must stay near 8, a real request must still get through, and the idle ones must be closed |
| shutdown | shutdown while a request is in flight and a keep-alive connection is idle |

## Hints (one at a time)

1. TCP is a stream of bytes, not of messages. One `recv()` can return half a
   request, or two and a half. Keep a buffer, and parse only once you can see
   `\r\n\r\n`.
2. The body is exactly `Content-Length` bytes after the blank line. Anything
   after that belongs to the next request, so don't throw it away.
3. `sock.settimeout(2)` limits *each* `recv()`. A client that sends one byte every
   second never trips it. Work out a deadline once (`time.monotonic() + 2`), and
   before each `recv()` set the timeout to the time *left*.
4. Check the size limit while you read, not after: a client can send 1 GB without
   a blank line.
5. A fixed pool of worker threads reading sockets from a `queue.Queue` bounds the
   thread count. The accept loop only accepts and enqueues.
6. A thread blocked in `accept()` or `recv()` doesn't notice a flag being set.
   Give `accept()` a short timeout so it checks the flag. For idle connections,
   `conn.shutdown(socket.SHUT_RDWR)` makes their blocked `recv()` return `b""`.
7. Got an error response that the client never sees? If you `close()` a socket
   with unread bytes still in it, the kernel sends a reset that can destroy the
   response in flight. Shut down the write side first, then drain briefly.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why one `recv()` is not one request, and what my buffer does about it:
- Per-recv timeout vs. a deadline for the whole head, and why Slowloris cares:
- Why a thread per connection fails, and what bounds mine:
- What graceful shutdown means, step by step:
- What my server still doesn't handle (chunked bodies? TLS? HTTP/2?):
