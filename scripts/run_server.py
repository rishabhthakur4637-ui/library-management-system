"""Run the development API and open Swagger after it is ready."""
import time
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn


DOCS_URL = "http://127.0.0.1:8000/docs"


def open_docs_when_ready():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(DOCS_URL, timeout=2) as response:
                if response.status == 200:
                    webbrowser.open("http://127.0.0.1:8000/")
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)

    print(f"API did not become ready. Open {DOCS_URL} after checking the server error above.")


if __name__ == "__main__":
    threading.Thread(target=open_docs_when_ready, daemon=True).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
