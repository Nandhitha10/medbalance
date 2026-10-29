"""Capture screenshots of MedBalance-Q UI using headless Chrome/Edge."""

import http.server
import os
from pathlib import Path
import socketserver
import subprocess
import threading
import time

PORT = 3333
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

DIST_DIR = str(Path(__file__).resolve().parents[2] / "web" / "dist")
SCREENS_DIR = str(Path(__file__).resolve().parent)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST_DIR, **kwargs)


def start_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()


def capture(url: str, output_path: str):
    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=1920,1080",
        "--virtual-time-budget=5000",
        f"--screenshot={output_path}",
        url,
    ]
    subprocess.run(cmd, check=True)


def main():
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    time.sleep(1.5)

    base_url = f"http://localhost:{PORT}"

    # 1. District Map
    map_png = os.path.join(SCREENS_DIR, "01_district_map.png")
    capture(f"{base_url}/?page=map", map_png)
    print(f"Captured: {map_png}")

    # 2. Facility Drawer
    drawer_png = os.path.join(SCREENS_DIR, "02_facility_drawer.png")
    capture(f"{base_url}/?page=map&facility=H3", drawer_png)
    print(f"Captured: {drawer_png}")

    # 3. Plan Page
    plan_png = os.path.join(SCREENS_DIR, "03_plan_page.png")
    capture(f"{base_url}/?page=plan", plan_png)
    print(f"Captured: {plan_png}")

    # 4. Ingestion / Review Queue
    ingest_png = os.path.join(SCREENS_DIR, "04_hospital_ingest.png")
    capture(f"{base_url}/?page=ingestion", ingest_png)
    print(f"Captured: {ingest_png}")

    print("All screenshots captured successfully.")


if __name__ == "__main__":
    main()
