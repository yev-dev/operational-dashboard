"""Runners package

Place runnable scripts (modules) here to be discovered by the dashboard.
Each module can define an argparse-based CLI in its __main__ context.

This package attempts to attach logging handlers to per-run log files when
launched by the dashboard. The dashboard sets environment variables:
  - DASHBOARD_CHILD_LOG_STDOUT: path to the stdout log file
  - DASHBOARD_CHILD_LOG_STDERR: path to the stderr log file
  - DASHBOARD_CHILD_LOG_LEVEL: desired logging level (e.g., INFO)

On import, we add file handlers to the root logger so that any module using
`logging.getLogger(__name__)` will emit into these files. If those variables
are not present, we fall back to a standard StreamHandler.
"""

from __future__ import annotations

import os
import logging


def _attach_dashboard_logging() -> None:
	try:
		lvl_name = str(os.environ.get("DASHBOARD_CHILD_LOG_LEVEL", "INFO")).upper()
		level = getattr(logging, lvl_name, logging.INFO)
	except Exception:
		level = logging.INFO

	root = logging.getLogger()
	# Set level regardless
	root.setLevel(level)

	fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

	stdout_path = os.environ.get("DASHBOARD_CHILD_LOG_STDOUT")
	stderr_path = os.environ.get("DASHBOARD_CHILD_LOG_STDERR")

	# Avoid duplicating handlers if already present
	existing_files = {getattr(h, "baseFilename", None) for h in root.handlers if hasattr(h, "baseFilename")}
	added = False

	try:
		if stdout_path and stdout_path not in existing_files:
			fh_out = logging.FileHandler(stdout_path, mode="a", encoding="utf-8")
			fh_out.setLevel(level)
			fh_out.setFormatter(fmt)
			root.addHandler(fh_out)
			added = True
		if stderr_path and stderr_path != stdout_path and stderr_path not in existing_files:
			fh_err = logging.FileHandler(stderr_path, mode="a", encoding="utf-8")
			fh_err.setLevel(level)
			fh_err.setFormatter(fmt)
			root.addHandler(fh_err)
			added = True
	except Exception:
		# Fall back to a stream handler below
		added = False

	if not added and not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
		sh = logging.StreamHandler()
		sh.setLevel(level)
		sh.setFormatter(fmt)
		root.addHandler(sh)


# Attempt attachment immediately on package import
try:
	_attach_dashboard_logging()
except Exception:
	# Do not crash if logging setup fails
	pass
