from __future__ import annotations

import os
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


def main() -> int:
    app_path = os.path.join(os.path.dirname(__file__), "app", "streamlit_app.py")
    port = int(os.environ.get("FISH_COUNTER_PORT", "8501"))
    url = f"http://localhost:{port}"
    open_browser = os.environ.get("FISH_COUNTER_OPEN_BROWSER", "0").lower() in {
        "1",
        "true",
        "yes",
    }

    cli_args = [
        "streamlit",
        "run",
        app_path,
        "--server.port",
        str(port),
        "--server.headless",
        "true",
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
