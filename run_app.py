from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser


def _open_browser_when_ready(url: str) -> None:
    for _ in range(60):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(url, timeout=1):
                pass
        except (urllib.error.URLError, TimeoutError):
            continue

        webbrowser.open(url)
        break


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

    if open_browser:
        threading.Thread(
            target=_open_browser_when_ready, args=(url,), daemon=True
        ).start()
    else:
        print(f"Fish Counter is running at {url}")

    if getattr(sys, "frozen", False):
        import streamlit.web.cli as stcli

        sys.argv = cli_args
        return int(stcli.main() or 0)

    process = subprocess.Popen(streamlit_cmd)
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
