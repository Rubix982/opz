"""Clinic API: books seats on the flu-shot clinic, and manages the on-call rota.

    POST /book?event=<id>&user=<name>       201 booked | 409 sold out
    POST /off-call?doctor=<name>            200 off call | 409 you're the last one on call
    GET  /state                             events, bookings and rota as JSON
    POST /reset?seats=<n>&events=<k>&shifts=<m>   reseed (labs only)

Two rules the business cares about:
  1. Never sell more bookings than an event has seats.
  2. Every shift always has at least one doctor on call.
"""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://clinic:clinic_FAKE_pw@db:5432/clinic")
# Stands in for the real work done between reading and writing: a payment
# check, a call to the scheduling system. It makes races easy to hit.
WORK_S = float(os.environ.get("WORK_SECONDS", "0.02"))

SCHEMA = """
DROP TABLE IF EXISTS bookings, events, doctors;
CREATE TABLE events   (id int PRIMARY KEY, name text NOT NULL, seats_left int NOT NULL);
CREATE TABLE bookings (id serial PRIMARY KEY, event_id int NOT NULL REFERENCES events, username text NOT NULL);
CREATE TABLE doctors  (name text PRIMARY KEY, shift int NOT NULL, on_call boolean NOT NULL);
"""


def connect() -> psycopg.Connection:
    # Postgres's default isolation level: READ COMMITTED.
    return psycopg.connect(DSN)


def reset(seats: int, events: int, shifts: int) -> None:
    with connect() as conn:
        conn.execute(SCHEMA)
        for e in range(1, events + 1):
            conn.execute("INSERT INTO events VALUES (%s, %s, %s)", (e, f"Flu clinic #{e}", seats))
        for s in range(1, shifts + 1):
            conn.execute("INSERT INTO doctors VALUES (%s, %s, true), (%s, %s, true)",
                         (f"alice-{s}", s, f"bob-{s}", s))


class SoldOut(Exception):
    pass


class LastOnCall(Exception):
    pass


def book(event_id: int, user: str) -> None:
    with connect() as conn:
        with conn.transaction():
            row = conn.execute("SELECT seats_left FROM events WHERE id = %s", (event_id,)).fetchone()
            if row is None or row[0] <= 0:
                raise SoldOut()
            time.sleep(WORK_S)  # payment check
            conn.execute("UPDATE events SET seats_left = %s WHERE id = %s", (row[0] - 1, event_id))
            conn.execute("INSERT INTO bookings (event_id, username) VALUES (%s, %s)", (event_id, user))


def go_off_call(doctor: str) -> None:
    with connect() as conn:
        with conn.transaction():
            row = conn.execute("SELECT shift FROM doctors WHERE name = %s", (doctor,)).fetchone()
            if row is None:
                raise LastOnCall()
            (on_call,) = conn.execute(
                "SELECT count(*) FROM doctors WHERE shift = %s AND on_call", (row[0],)
            ).fetchone()
            if on_call < 2:
                raise LastOnCall()
            time.sleep(WORK_S)  # tell the scheduling system
            conn.execute("UPDATE doctors SET on_call = false WHERE name = %s", (doctor,))


def state() -> dict:
    with connect() as conn:
        events = conn.execute(
            "SELECT e.id, e.seats_left, count(b.id) FROM events e LEFT JOIN bookings b ON b.event_id = e.id "
            "GROUP BY e.id ORDER BY e.id"
        ).fetchall()
        rota = conn.execute(
            "SELECT shift, count(*) FILTER (WHERE on_call) FROM doctors GROUP BY shift ORDER BY shift"
        ).fetchall()
    return {
        "events": [{"id": i, "seats_left": s, "bookings": b} for i, s, b in events],
        "on_call_per_shift": {str(s): n for s, n in rota},
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/state":
            self._send(200, state())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/book":
                book(int(q["event"]), q.get("user", "anon"))
                self._send(201, {"booked": True})
            elif url.path == "/off-call":
                go_off_call(q["doctor"])
                self._send(200, {"off_call": True})
            elif url.path == "/reset":
                reset(int(q.get("seats", "5")), int(q.get("events", "1")), int(q.get("shifts", "1")))
                self._send(200, {"reset": True})
            else:
                self._send(404, {"error": "not found"})
        except SoldOut:
            self._send(409, {"error": "sold out"})
        except LastOnCall:
            self._send(409, {"error": "someone has to stay on call"})
        except psycopg.Error as e:
            print(f"database error: {type(e).__name__}: {e}".strip(), flush=True)
            self._send(500, {"error": type(e).__name__})

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    print("clinic API on :8040", flush=True)
    ThreadingHTTPServer.request_queue_size = 256  # room for the load tests' bursts
    ThreadingHTTPServer(("0.0.0.0", 8040), Handler).serve_forever()
