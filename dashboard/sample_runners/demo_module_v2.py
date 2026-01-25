#!/usr/bin/env python3
"""Dummy multi-threaded runner for dashboard testing.

Starts N worker threads that each print a timestamped message to stdout and
emit a logging message (stderr) every `interval_seconds` for `duration_minutes`.

Usage:
  python dummy_model_v2.py --threads 5 --interval-seconds 10 --duration-minutes 60
"""

from __future__ import annotations

import argparse
import logging
import threading
import time
from datetime import datetime


def worker(thread_id: int, interval: float, end_time: float, stop_event: threading.Event, msg_prefix: str) -> None:
    """Worker thread: prints to stdout and logs to stderr at each interval until end_time or stop_event."""
    iter_count = 0
    while not stop_event.is_set() and time.time() < end_time:
        iter_count += 1
        ts = datetime.now().isoformat(sep=" ", timespec="seconds")
        # stdout message (print)
        print(f"{ts} [{msg_prefix}] THREAD-{thread_id} iteration={iter_count} - stdout message", flush=True)
        # stderr/log message
        logging.info(f"{msg_prefix} THREAD-{thread_id} iteration={iter_count} - stderr/log message")
        # Wait for next interval, but exit early if stop_event set
        remaining = end_time - time.time()
        if remaining <= 0:
            break
        wait = min(interval, remaining)
        stop_event.wait(wait)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="dummy_model_v2", description="Dummy multi-threaded runner for dashboard testing")
    p.add_argument("--threads", type=int, default=5, help="Number of worker threads to start")
    p.add_argument("--interval-seconds", type=float, default=10.0, help="Interval between messages in seconds")
    p.add_argument("--duration-minutes", type=float, default=60.0, help="Total duration to run in minutes")
    p.add_argument("--message", type=str, default="DUMMY", help="Message prefix to include in outputs")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    num_threads = max(1, int(args.threads))
    interval = float(args.interval_seconds)
    duration_minutes = float(args.duration_minutes)
    msg_prefix = args.message

    total_seconds = max(0.0, duration_minutes * 60.0)
    end_time = time.time() + total_seconds

    # Configure logging to stderr
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    logging.info("Starting dummy_model_v2: threads=%d interval=%.1fs duration=%.1fmin prefix=%s", num_threads, interval, duration_minutes, msg_prefix)
    print(f"Starting dummy_model_v2: threads={num_threads} interval={interval}s duration={duration_minutes}min prefix={msg_prefix}")

    try:
        for i in range(num_threads):
            th = threading.Thread(target=worker, args=(i + 1, interval, end_time, stop_event, msg_prefix), daemon=True)
            th.start()
            threads.append(th)

        # Wait until all threads finish or interrupted
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, stopping...", flush=True)
        logging.info("Received KeyboardInterrupt, stopping...")
        stop_event.set()
    finally:
        # Ensure threads are joined
        for t in threads:
            t.join(timeout=1.0)

    logging.info("dummy_model_v2 finished")
    print("dummy_model_v2 finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
