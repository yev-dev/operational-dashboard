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
from datetime import date, timedelta
from typing import Iterable, List, Optional


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


def _daterange(start: date, end: date) -> Iterable[date]:
    """Yield dates from start to end inclusive.

    Caps total iterations to avoid long runs when users pass wide ranges.
    """
    max_days = 31
    if start > end:
        return []
    delta = (end - start).days
    days = min(delta, max_days - 1)
    for n in range(days + 1):
        yield start + timedelta(days=n)


def sample_script(operations: List[str],
                  start_date: Optional[date],
                  end_date: Optional[date],
                  upload_start_date: Optional[date],
                  upload_end_date: Optional[date],
                  period_date: Optional[date] = None) -> int:
    """Simulate sample operations used by runners.

    operations: list of strings from the allowed set: create-benchmarks, create-upload-list
    Dates are datetime.date objects or None. The function will print/log simulated outputs so the dashboard
    can capture and display them.
    """
    logger = logging.getLogger("sample_script")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    logger.info("sample_script starting: operations=%s start=%s end=%s upload_start=%s upload_end=%s period=%s",
                operations, start_date, end_date, upload_start_date, upload_end_date, period_date)

    allowed = {"create-benchmarks", "create-upload-list"}
    for op in operations:
        if op not in allowed:
            logger.error("Unknown operation requested: %s", op)
            return 2

    try:
        for op in operations:
            logger.info("Starting operation: %s", op)
            print(f"OPERATION: {op}")

            if op == "create-benchmarks":
                if not (start_date and end_date):
                    logger.error("create-benchmarks requires --start-date and --end-date")
                    return 3
                items = list(_daterange(start_date, end_date))[:5]
                for i, d in enumerate(items, start=1):
                    msg = f"benchmark: id={i} date={d.isoformat()} period={period_date.isoformat() if period_date else 'N/A'}"
                    logger.info(msg)
                    print(msg, flush=True)
                    time.sleep(0.2)

            elif op == "create-upload-list":
                # upload list may use separate upload_start/upload_end if provided
                usd = upload_start_date or start_date
                ued = upload_end_date or end_date
                if not (usd and ued):
                    logger.error("create-upload-list requires either upload-start/upload-end or start/end dates")
                    return 4
                items = list(_daterange(usd, ued))[:5]
                for i, d in enumerate(items, start=1):
                    msg = f"upload-item: file=upload_{d.isoformat()}.csv date={d.isoformat()}"
                    logger.info(msg)
                    print(msg, flush=True)
                    time.sleep(0.15)

            logger.info("Finished operation: %s", op)

        logger.info("sample_script completed")
        return 0

    except KeyboardInterrupt:
        logger.info("sample_script interrupted by user")
        return 130


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dummy model and sample script that writes logs for testing.")
    sub = parser.add_argument_group("dummy", "Run the heartbeat dummy model")
    sub.add_argument("--duration", type=int, default=60, help="Total run time in seconds (default: 60)")
    sub.add_argument("--interval", type=int, default=10, help="Interval between log messages in seconds (default: 10)")

    # sample_script args
    parser.add_argument("--operations", "-o", nargs="+", choices=["create-benchmarks", "create-upload-list"],
                        help="One or more operations to run: create-benchmarks, create-upload-list")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD) for operations that need a start date")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD) for operations that need an end date")
    parser.add_argument("--upload-start-date", type=str, help="Upload list start date (YYYY-MM-DD)")
    parser.add_argument("--upload-end-date", type=str, help="Upload list end date (YYYY-MM-DD)")
    parser.add_argument("--period-date", type=str, default=None, help="Optional period date (YYYY-MM-DD)")

    args = parser.parse_args()

    # operations is required for the sample script; throw an argparse-style argument error if missing
    if not args.operations:
        parser.error("Missing required argument --operations: provide one or more of create-benchmarks, create-upload-list")

    def _parse_date(s: Optional[str]) -> Optional[date]:
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            parser.error(f"Invalid date format: {s}. Expected YYYY-MM-DD")

    ops: List[str] = args.operations
    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)
    upload_start_date = _parse_date(args.upload_start_date)
    upload_end_date = _parse_date(args.upload_end_date)
    period_date = _parse_date(args.period_date)

    raise SystemExit(sample_script(ops, start_date, end_date, upload_start_date, upload_end_date, period_date))
