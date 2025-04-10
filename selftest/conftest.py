# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.
# --------------------------------------------------------------------------

"""pytest configuration for selftest."""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


# pylint: disable=unused-argument


def pytest_sessionstart(session):
    """Initialize session attributes that are marked on finish."""
    session.aborted = False
    session.failed = False


def pytest_sessionfinish(session, exitstatus):
    """Mark test session as aborted or failed."""
    if exitstatus == 2:  # Interrupted (e.g., Ctrl+C)
        session.aborted = True
    elif exitstatus != 0:
        session.failed = True


def pytest_configure(config):
    """Configure pytest logging and artifacts directory.

    Create artifacts directory based on the current timestamp if not configured.
    This is used to store logs and other artifacts generated during the test run.
    If running under pytest-xdist, use the worker ID to create separate logs for each worker.
    """
    artifacts_path = os.getenv("SELFTEST_ARTIFACTS_PATH")
    if "PYTEST_XDIST_WORKER" not in os.environ:
        if not artifacts_path:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            artifacts_path = f"/tmp/selftest-{timestamp}"
            os.environ["SELFTEST_ARTIFACTS_PATH"] = artifacts_path
        print(f"artifacts={artifacts_path}", file=sys.stderr)

    artifacts_path = os.getenv("SELFTEST_ARTIFACTS_PATH")
    assert artifacts_path, "SELFTEST_ARTIFACTS_PATH must be set"

    log_path = Path(artifacts_path)
    log_path.mkdir(parents=True, exist_ok=True)

    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_id is not None:
        logging.basicConfig(
            format="%(asctime)s [%(levelname)s] %(message)s",
            filename=log_path / f"{worker_id}.log",
            level=logging.DEBUG,
        )
    else:
        logging.basicConfig(
            format="%(asctime)s [%(levelname)s] %(message)s",
            filename=log_path / "main.log",
            level=logging.DEBUG,
        )
        logger.debug("test")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Group tests by vm_size for pytest-xdist to avoid quota issues."""
    for item in items:
        vm_size = (
            item.callspec.params.get("vm_size", None)
            if hasattr(item, "callspec")
            else None
        )
        if vm_size:
            item.add_marker(pytest.mark.xdist_group(vm_size))
