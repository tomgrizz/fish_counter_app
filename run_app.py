from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


def main() -> int:
    app_path = os.path.join(os.path.dirname(__file__), "app", "streamlit_app.py")
    port = int(os.environ.get("FISH_COUNTER_PORT", "8501"))
    url = f"http://localhost:{port}"

    streamlit_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        app_path,
        "--server.port",
        str(port),
        "--server.headless",
        "true",
    ]

    process = subprocess.Popen(streamlit_cmd)

    browser_opened = False
    for _ in range(60):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(url, timeout=1):
                pass
        except (urllib.error.URLError, TimeoutError):
            continue

        if not browser_opened:
            webbrowser.open(url)
            browser_opened = True
            break

    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
