from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser


def _open_browser_when_ready(url: str, show_failure_notice: bool) -> None:
    for _ in range(60):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(url, timeout=1):
                pass
        except (urllib.error.URLError, TimeoutError):
            continue

        webbrowser.open(url)
        break
    else:
        _notify_startup_failure(url, show_failure_notice)


def _notify_startup_failure(url: str, show_failure_notice: bool) -> None:
    message = (
        "Fish Counter Review started but the local web server did not respond.\n"
        f"Try opening {url} manually in your browser.\n"
        "If the page still does not load, restart the app and check the log file for "
        "errors."
    )

    log_path = _get_log_path()
    _log_message(message)
    _log_message(f"Log file: {log_path}")

    if not show_failure_notice:
        return

    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Fish Counter Review", 0x10)
    except Exception:
        _log_message("Failed to show Windows error dialog.")


def _get_log_path() -> str:
    base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    log_dir = os.path.join(base_dir, "FishCounterReview", "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "launcher.log")


def _log_message(message: str) -> None:
    try:
        log_path = _get_log_path()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def _select_port(preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred_port))
            return preferred_port
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]


def _select_port(preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred_port))
            return preferred_port
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]


def main() -> int:
    app_path = os.path.join(os.path.dirname(__file__), "app", "streamlit_app.py")
    preferred_port = int(os.environ.get("FISH_COUNTER_PORT", "8501"))
    port = _select_port(preferred_port)
    url = f"http://127.0.0.1:{port}"
    default_open = "1" if getattr(sys, "frozen", False) else "0"
    open_browser = os.environ.get("FISH_COUNTER_OPEN_BROWSER", default_open).lower() in {
        "1",
        "true",
        "yes",
    }
    show_failure_notice = getattr(sys, "frozen", False)
    _log_message(
        f"Starting Fish Counter Review on {url} (open_browser={open_browser})."
    )

    headless_mode = "false" if open_browser else "true"
    cli_args = [
        "streamlit",
        "run",
        app_path,
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        headless_mode,
        "--global.developmentMode",
        "false",
    ]
    streamlit_cmd = [
        sys.executable,
        "-m",
        *cli_args,
    ]
    _log_message(f"Streamlit args: {' '.join(cli_args)}")

    if open_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(url, show_failure_notice),
            daemon=True,
        ).start()
    else:
        print(f"Fish Counter is running at {url}")

    if getattr(sys, "frozen", False):
        import streamlit.web.cli as stcli

        sys.argv = cli_args
        log_path = _get_log_path()
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                original_stdout = sys.stdout
                original_stderr = sys.stderr
                sys.stdout = handle
                sys.stderr = handle
                try:
                    return int(stcli.main() or 0)
                finally:
                    sys.stdout = original_stdout
                    sys.stderr = original_stderr
        except Exception as error:
            _log_exception("Streamlit failed to start", error)
            _notify_startup_failure(url, show_failure_notice)
            return 1

    process = subprocess.Popen(streamlit_cmd)
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
