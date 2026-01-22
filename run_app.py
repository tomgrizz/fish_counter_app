from __future__ import annotations

import os
import subprocess
import sys
import time
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

    for _ in range(30):
        time.sleep(0.5)
        try:
            webbrowser.open(url)
            break
        except Exception:
            continue

    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
