"""
Dev runner: starts uvicorn (with reload) + Vite dev server in parallel.
Both processes write to log.txt (appended). A single Ctrl-C kills both.

Usage: .venv/bin/python dev.py
"""
import os
import signal
import subprocess
import sys

import log

log.setup()

import logging
_log = logging.getLogger("dev")

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = open(log.LOG_FILE, "a", encoding="utf-8")

procs = []


def _kill_all():
    for p in procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass


def _sigint(sig, frame):
    _log.info("shutting down…")
    _kill_all()
    LOG_FILE.close()
    sys.exit(0)


signal.signal(signal.SIGINT, _sigint)
signal.signal(signal.SIGTERM, _sigint)

backend = subprocess.Popen(
    [
        os.path.join(ROOT, ".venv/bin/python"), "-m", "uvicorn", "api.main:app",
        "--reload", "--port", "8000",
        "--log-config", "/dev/null",  # suppress uvicorn's own log setup; root logger handles it
    ],
    cwd=ROOT,
    stdout=LOG_FILE,
    stderr=LOG_FILE,
    start_new_session=True,
)

frontend = subprocess.Popen(
    ["npm", "run", "dev"],
    cwd=os.path.join(ROOT, "web"),
    stdout=LOG_FILE,
    stderr=LOG_FILE,
    start_new_session=True,
)

procs.extend([backend, frontend])

_log.info("backend  → http://localhost:8000")
_log.info("frontend → http://localhost:5173")
_log.info("Ctrl-C to stop both")

# Wait for backend; if it exits (crash/reload), kill everything
backend.wait()
_kill_all()
LOG_FILE.close()
