#!/usr/bin/env python3
"""
third_model.py

Accepts parameters without argparse as plain string tokens and/or environment variables.

Supported inputs (any subset, any string format):
- RUN_DATE:any-string
- COB_DATE:any-string
- START_DATE:any-string
- END_DATE:any-string

Behavior:
- Extracts date strings from argv tokens (format NAME:VALUE) or from environment
  variables (NAME). When both exist, argv takes precedence.
- Concatenates all provided date strings in the fixed order
  [RUN_DATE, COB_DATE, START_DATE, END_DATE], separated by ':'.
- Prints the concatenated string to stdout.

Usage examples:
    python -m runners.third_model RUN_DATE:2025-01-01 START_DATE:2025-01-01 END_DATE:2025-12-31
    RUN_DATE=2025-01-01 COB_DATE=2025-01-02 python -m runners.third_model
    # Any string formats are accepted, e.g.
    python -m runners.third_model RUN_DATE:2025/01/01  COB_DATE:Jan-02-2025  START_DATE:2025.01.01  END_DATE:2025_12_31

Note: No argparse is used; this script is compatible with the dashboard's
"no-argparse" mode and can also receive values via env vars through the
subprocess launcher.
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime
from typing import Dict, Optional

KEYS = ["RUN_DATE", "COB_DATE", "START_DATE", "END_DATE"]


def parse_tokens(argv: list[str]) -> Dict[str, str]:
    """Parse NAME:VALUE tokens from argv into a dict.

    Tokens must contain a colon ':'; only recognized KEYS are stored.
    """
    out: Dict[str, str] = {}
    for tok in argv:
        if ":" not in tok:
            continue
        name, value = tok.split(":", 1)
        name = name.strip().upper()
        if name in KEYS:
            out[name] = value.strip()
    return out


def get_env(name: str) -> Optional[str]:
    val = os.environ.get(name)
    if val is None:
        return None
    return val.strip()


def main(argv: list[str]) -> int:
    # Initialize logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("third_model")

    start_time = time.perf_counter()
    logger.info("Process started")

    # First, parse argv tokens
    params = parse_tokens(argv)

    # Fallback to environment variables for missing keys
    for k in KEYS:
        if k not in params:
            env_val = get_env(k)
            if env_val:
                params[k] = env_val

    # Build concatenation in fixed order, include only provided values
    values = [params[k] for k in KEYS if k in params and params[k] != ""]
    if not values:
        print("[third_model] No date values provided via argv or environment.")
        print("[third_model] Expected tokens like 'RUN_DATE:YYYY-MM-DD' or env vars RUN_DATE, COB_DATE, START_DATE, END_DATE.")
        return 0

    result = ":".join(values)

    # Simulate a calculation for ~60 seconds in a background thread
    def _simulate_calculation(duration_sec: int = 60, report_every_sec: int = 5) -> None:
        t0 = time.perf_counter()
        next_report = report_every_sec
        while True:
            elapsed = time.perf_counter() - t0
            if elapsed >= duration_sec:
                break
            # Periodic progress messages
            if elapsed >= next_report:
                logger.info("Simulated computation... %.0f/%.0f seconds", elapsed, duration_sec)
                next_report += report_every_sec
            time.sleep(0.2)
        logger.info("Simulated computation completed (%.2f seconds)", elapsed)

    worker = threading.Thread(target=_simulate_calculation, kwargs={"duration_sec": 60, "report_every_sec": 5}, daemon=False)
    worker.start()
    worker.join()

    elapsed_total = time.perf_counter() - start_time
    logger.info("Process finished in %.2f seconds at %s", elapsed_total, datetime.now().isoformat(timespec="seconds"))

    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
