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


def _open_browser_when_ready(port: int, log: logging.Logger) -> None:
    """Background thread target — wait for the server to bind, then
    open the default browser. Runs concurrent with uvicorn on the main
    thread.

    Failures here are non-fatal: the user can navigate to the URL
    manually if the auto-open misfires (e.g. no default browser
    configured, or running on a headless server).
    """
    url = f"http://127.0.0.1:{port}/"
    if _wait_until_ready(port):
        log.info("Server ready; opening browser at %s", url)
    else:
        log.warning("Server didn't open port within timeout; opening browser anyway at %s", url)
    try:
        webbrowser.open(url)
    except Exception:
        log.exception("Could not open default browser; user can navigate to %s manually", url)


def _ensure_stdio() -> None:
    """Make sure sys.stdout / sys.stderr are not None.

    In a PyInstaller windowed build (``console=False``) Windows runs
    the binary with no allocated console, so the Python runtime sets
    ``sys.stdout = None`` and ``sys.stderr = None``. Code that
    introspects these streams blows up — most relevantly uvicorn's
    default logger, which calls ``isatty()`` on stderr at import time
    and crashes with ``AttributeError: 'NoneType' object has no
    attribute 'isatty'``.

    Routing the streams to ``os.devnull`` (the Windows equivalent is
    transparently mapped) is the standard PyInstaller workaround.
    Anything our app writes to stdout/stderr is already redundant with
    the rotating file logger set up by ``_setup_logging`` — these
    streams should normally be unused in production.
    """
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> int:
    # MUST run before anything that touches stdio (uvicorn's default
    # logger reads sys.stderr at import time).
    _ensure_stdio()

    log_path = _setup_logging()
    log = logging.getLogger("processarc.desktop")
    log.info("ProcessArc desktop launcher starting (log: %s)", log_path)

    # On Windows + Python 3.11, the default asyncio event loop policy
    # is the Proactor loop. Uvicorn historically required the Selector
    # loop on Windows; modern uvicorn supports either but the Selector
    # loop is its proven-stable default and matches dev behavior.
    # Setting this BEFORE importing uvicorn keeps any module-level
    # loop selection from latching onto the Proactor.
    if sys.platform == "win32":
        try:
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            log.info("Set Windows asyncio policy to Selector")
        except Exception:
            log.exception("Failed to set Windows asyncio Selector policy; continuing with default")

    try:
        log.info("Importing uvicorn + FastAPI app...")
        import uvicorn
        from backend.api.main import app  # imports the FastAPI app
        log.info("Imports OK")
    except Exception:
        log.exception("Failed to import backend.api.main; the .exe build is broken.")
        return 1

    port = _pick_port()
    url = f"http://127.0.0.1:{port}/"
    log.info("Selected port %d; URL %s", port, url)

    # Browser opener runs in a daemon thread so it doesn't block uvicorn.
    # uvicorn itself MUST run on the main thread on Windows — running it
    # from a thread has been observed to hang silently during startup
    # (signal-handler installation and event-loop selection have main-
    # thread assumptions that don't always raise when violated). The
    # tradeoff: Ctrl+C handling is uvicorn's job rather than ours, which
    # is what we want anyway in a windowless desktop build.
    threading.Thread(
        target=_open_browser_when_ready,
        args=(port, log),
        name="browser-opener",
        daemon=True,
    ).start()

    log.info("Building uvicorn config and starting server (blocking)...")
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info",
            access_log=False,
        )
    except SystemExit:
        # uvicorn raises SystemExit on its own clean shutdown path.
        log.info("uvicorn requested SystemExit; shutting down cleanly")
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt; shutting down cleanly")
    except Exception:
        log.exception("uvicorn crashed during run(); exiting non-zero")
        return 1

    log.info("ProcessArc desktop launcher exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
