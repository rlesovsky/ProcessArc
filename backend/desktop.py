"""Desktop launcher — PyInstaller entry point for ProcessArc.exe.

What this module does, in order, when the .exe is double-clicked:

1. Set up rotating-file logging under the user-data dir so any crash is
   recoverable post-mortem (no console window is shown in the bundled
   build, so stdout/stderr would be invisible otherwise).
2. Pick a free TCP port (try 8765 first, fall back to OS-assigned).
3. Start uvicorn in a background thread with the FastAPI app from
   ``backend.api.main`` — which serves both the API and the built
   React UI from the same origin (see ``main.py``'s ``_dist`` mount).
4. Open the user's default browser to ``http://localhost:<port>/``.
5. Block the main thread on the uvicorn server; exit cleanly on Ctrl+C
   or when the server stops.

Dev mode is unaffected — ``uvicorn backend.api.main:app --reload`` still
works exactly as before. This module is *only* used by the PyInstaller
build and is safe to import elsewhere only if you want to spawn the
same launcher (e.g. for a smoke test of the bundled-style behavior on
your dev machine).
"""

from __future__ import annotations

import logging
import logging.handlers
import socket
import sys
import threading
import time
import webbrowser
from contextlib import closing
from pathlib import Path

# We deliberately import the FastAPI app lazily, after the path/log
# bootstrap has run, so that any import-time exception lands in our log
# file rather than vanishing into the hidden console.


# ────────────────────────────────────────────────────────────────────────────
# User data directory + logging
# ────────────────────────────────────────────────────────────────────────────


def _user_data_dir() -> Path:
    """Match ``backend.settings.config._user_data_dir`` (kept in sync by hand).

    We don't import the config module here because we want to set up
    logging *before* any backend import runs — so if backend imports
    blow up, the traceback lands in app.log.
    """
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "ProcessArc"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ProcessArc"
    import os
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "processarc"


def _setup_logging() -> Path:
    """Configure a rotating log file under <user-data-dir>/logs/app.log.

    Returns the log file path so the boot banner can print it (only
    useful when the console *is* visible, e.g. when running the
    launcher manually from a terminal during local testing).
    """
    log_dir = _user_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Quiet uvicorn's access spam in the file; keep error+info from
    # uvicorn's own server module so startup/shutdown is recorded.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return log_path


# ────────────────────────────────────────────────────────────────────────────
# Port selection
# ────────────────────────────────────────────────────────────────────────────


PREFERRED_PORT = 8765  # uncommon enough to usually be free; not 8000 so it
                        # doesn't collide with dev uvicorn if the engineer
                        # happens to be running both.


def _port_is_free(port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _pick_port() -> int:
    """Return PREFERRED_PORT if free, else an OS-assigned free port."""
    if _port_is_free(PREFERRED_PORT):
        return PREFERRED_PORT
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ────────────────────────────────────────────────────────────────────────────
# Server boot
# ────────────────────────────────────────────────────────────────────────────


def _wait_until_ready(port: int, timeout: float = 10.0) -> bool:
    """Poll the port until something is listening, or give up.

    We use this to gate the browser-open until uvicorn is actually
    accepting connections — otherwise the user sees a momentary
    'connection refused' error in their browser.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.settimeout(0.2)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except OSError:
                time.sleep(0.1)
    return False


def main() -> int:
    log_path = _setup_logging()
    log = logging.getLogger("processarc.desktop")
    log.info("ProcessArc desktop launcher starting (log: %s)", log_path)

    try:
        import uvicorn
        from backend.api.main import app  # imports the FastAPI app
    except Exception:
        log.exception("Failed to import backend.api.main; the .exe build is broken.")
        return 1

    port = _pick_port()
    url = f"http://127.0.0.1:{port}/"
    log.info("Selected port %d; URL %s", port, url)

    # On Windows + Python 3.11, the default asyncio event loop policy
    # is the Proactor loop. Uvicorn historically required the Selector
    # loop on Windows; modern uvicorn handles either but exceptions
    # raised during startup with the Proactor loop have been observed
    # to vanish silently from background threads (no traceback hits
    # stderr because there's no console). Force the Selector loop on
    # Windows for parity with the dev environment and predictable
    # error handling.
    if sys.platform == "win32":
        import asyncio
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            log.info("Set Windows asyncio policy to Selector")
        except Exception:
            log.exception("Failed to set Windows asyncio Selector policy; continuing with default")

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
        # Explicit loop=asyncio prevents uvicorn from trying to import
        # uvloop (which doesn't exist on Windows but would emit a
        # noisy warning) and pins behavior across platforms.
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    def _run_server() -> None:
        """Background thread target — catches and logs anything uvicorn
        throws so we don't get a hung process with no diagnostic.

        Without this wrapper, exceptions in a daemon thread silently
        terminate the thread and stdout/stderr go nowhere in a hidden-
        console build, leaving the main thread waiting on a port that
        will never bind.
        """
        try:
            server.run()
        except Exception:
            log.exception("uvicorn server crashed during run()")

    # Run uvicorn in a background thread so we can open the browser
    # once it's ready, and so Ctrl+C / window close lands cleanly.
    server_thread = threading.Thread(
        target=_run_server, name="uvicorn", daemon=True
    )
    server_thread.start()

    if _wait_until_ready(port):
        log.info("Server ready; opening browser at %s", url)
        try:
            webbrowser.open(url)
        except Exception:
            log.exception("Could not open default browser; user can navigate to %s manually", url)
    else:
        if not server_thread.is_alive():
            log.error("Server thread died before binding the port; see traceback above. Exiting.")
            return 1
        log.error("Server did not become ready within timeout; opening browser anyway")
        webbrowser.open(url)

    # Block until the server stops (e.g. Ctrl+C in a visible-console
    # build, or some other shutdown signal). In a windowed build the
    # user closing the browser tab does NOT stop the server — the .exe
    # keeps running in the background. They'd kill it via Task Manager.
    # That's the standard tradeoff for "windowless server-style"
    # desktop apps; we accept it for v1 and can layer on a system-tray
    # icon later if it matters.
    try:
        server_thread.join()
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt; asking uvicorn to shut down")
        server.should_exit = True
        server_thread.join(timeout=5)

    log.info("ProcessArc desktop launcher exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
