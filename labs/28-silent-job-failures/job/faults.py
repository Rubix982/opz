"""Fault injection for check.sh. Leave this file and its call in place.

JOB_CRASH_AFTER_ROWS=N makes the process die abruptly after writing N rows,
the way it would if the machine ran out of memory or was rebooted mid-run.
"""

import os


def maybe_crash(rows_written: int) -> None:
    limit = os.environ.get("JOB_CRASH_AFTER_ROWS")
    if limit is not None and rows_written >= int(limit):
        os._exit(137)  # no cleanup, no exception handler, no finally: like SIGKILL
