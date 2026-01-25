"""
Dummy runner for dashboard testing.

This script simulates a long-running model by writing periodic logging messages
and stdout prints so the dashboard log tail / per-process log viewer can pick them up.

Usage:
  python -m qf.dashboard.runners.dummy_model --duration 60 --interval 10

Arguments:
  --duration: total run time in seconds (default: 60)
  --interval: how often to log/print in seconds (default: 10)
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime


def main(duration: int = 60, interval: int = 10) -> int:
    logger = logging.getLogger("dummy_model")
    # Configure logger to output to stdout if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    logger.info("dummy_model starting: duration=%s interval=%s", duration, interval)
    start = time.time()
    next_tick = start
    try:
        while True:
            now = time.time()
            if now >= next_tick:
                elapsed = int(now - start)
                msg = f"heartbeat: elapsed={elapsed}s ({datetime.now().isoformat(timespec='seconds')})"
                # Log and print so both stdout and logging outputs are available
                logger.info(msg)
                print(msg, flush=True)
                next_tick += interval
            if now - start >= duration:
                break
            # Sleep a short while to be responsive
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("dummy_model interrupted by user")
        return 130

    logger.info("dummy_model finished after %s seconds", int(time.time() - start))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dummy model that writes periodic logs for testing.")
    parser.add_argument("--duration", type=int, default=60, help="Total run time in seconds (default: 60)")
    parser.add_argument("--interval", type=int, default=10, help="Interval between log messages in seconds (default: 10)")
    args = parser.parse_args()
    raise SystemExit(main(duration=args.duration, interval=args.interval))
