"""Import the real files already checked into BhoomiAI (local-only).

Requires running FastAPI and a local administrator account. This script does
not upload data to GitHub or any third-party service. Idempotent by layer name,
scene title and document filename. No dummy observations are generated.

From the repo root (Windows PowerShell):
    .\\backend\\.venv\\Scripts\\python.exe backend/scripts/import_ghaziabad.py
"""
from __future__ import annotations

import argparse
import getpass
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = ROOT / "datasets/gis/boundaries/uttar_pradesh/Ghaziabad_Boundary.geojson"
WORLD_COVER = ROOT / "datasets/satellite/esa_worldcover/2021/original/Ghaziabad_WorldCover_2021.tif.tif"
REPORTS = ROOT / "datasets/dilrmp/Uttar Pradesh/state_reports"
SOURCE_BOUNDARY = "https://onlinemaps.surveyofindia.gov.in/"
SOURCE_WORLDCOVER = "https://esa-worldcover.org/en/data-access"
SOURCE_DILRMP = "https://dilrmp.gov.in/reports/download-progress-report"
LAYER_NAME = "Ghaziabad district boundary (Survey of India)"
SCENE_TITLE = "ESA WorldCover 2021 - Ghaziabad (annual composite)"


def request(client, method, url, **kwargs):
    response = client.request(method, url, **kwargs)
    if response.status_code >= 400:
        try:
            message = response.json().get("detail", response.text[:300])
        except ValueError:
            message = response.text[:300]
        raise RuntimeError(f"{method} {url}: HTTP {response.status_code}: {message}")
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="Local FastAPI base URL")
    parser.add_argument("--dry-run", action="store_true", help="Show discovered files only")
    parser.add_argument("--skip-reports", action="store_true", help="Import spatial data only")
    args = parser.parse_args()
    sheets = sorted(REPORTS.glob("*.xlsx"))
    print(f"Boundary: {BOUNDARY if BOUNDARY.is_file() else 'MISSING'}")
    print(f"Land cover: {WORLD_COVER if WORLD_COVER.is_file() else 'MISSING'}")
    print(f"DILRMP Uttar Pradesh state-wide sheets ({len(sheets)}):")
    for path in sheets:
        print(f"  {path.name} ({path.stat().st_size / 1048576:.1f} MB)")
    if args.dry_run:
        return 0

    email = input("BhoomiAI administrator email: ").strip()
    password = getpass.getpass("BhoomiAI password (hidden): ")
    with httpx.Client(base_url=args.api.rstrip("/"), timeout=120.0) as client:
        login = request(client, "POST", "/platform/auth/login",
                        json={"email": email, "password": password})
        if login["user"]["role"] != "admin":
            raise RuntimeError("Only the administrator can run this local bootstrap import.")
        client.headers["Authorization"] = "Bearer " + login["access_token"]

        if BOUNDARY.is_file():
            layers = request(client, "GET", "/gis/layers")
            if any(item["name"] == LAYER_NAME for item in layers):
                print("[SKIP] Ghaziabad boundary already imported")
            else:
                with BOUNDARY.open("rb") as handle:
                    data = request(
                        client, "POST", "/gis/layers",
                        files={"file": (BOUNDARY.name, handle, "application/geo+json")},
                        data={
                            "name": LAYER_NAME, "source_url": SOURCE_BOUNDARY,
                            "licence": "Check Survey of India source reuse conditions",
                            "description": "Official Uttar Pradesh district polygon; DISTRICT=GHAZIABAD. "
                                           "Exported from QGIS in WGS84 longitude/latitude.",
                        },
                    )
                print(f"[OK] Imported boundary: {data['features']} feature(s)")
        else:
            print("[SKIP] Boundary file not found")

        if WORLD_COVER.is_file():
            scenes = request(client, "GET", "/raster/scenes")
            if any(item["title"] == SCENE_TITLE for item in scenes):
                print("[SKIP] WorldCover raster already imported")
            else:
                with WORLD_COVER.open("rb") as handle:
                    data = request(
                        client, "POST", "/raster/scenes",
                        files={"file": (WORLD_COVER.name, handle, "image/tiff")},
                        data={
                            "title": SCENE_TITLE,
                            # Required date field stores the END of the product
                            # reference year; NOT a satellite acquisition date.
                            "capture_date": "2021-12-31",
                            "platform": "ESA WorldCover annual composite (2021; date=year-end placeholder)",
                            "source_url": SOURCE_WORLDCOVER,
                            "licence": "Check ESA WorldCover product terms",
                        },
                    )
                print(f"[OK] Imported ESA WorldCover: {data['bands']} band(s)")
        else:
            print("[SKIP] Clipped WorldCover file not found")

        if args.skip_reports:
            print("Spatial import complete. Open GIS Explorer and calculate land-cover statistics.")
            return 0

        indexed = request(client, "GET", "/documents")
        names = {d["filename"] for d in indexed}
        # Older importer versions mistakenly labelled state-wide workbooks as
        # Ghaziabad-only. Correct known filenames using the audited admin API.
        current_by_filename = {d["filename"]: d for d in indexed}
        for path in sheets:
            prior = current_by_filename.get(path.name)
            if prior and (prior.get("district") or prior.get("title", "").startswith("DILRMP Ghaziabad")):
                request(client, "PATCH", f"/documents/{prior['id']}/metadata", json={
                    "title": "DILRMP Uttar Pradesh: " + path.stem,
                    "state": "Uttar Pradesh", "district": "",
                    "source_url": SOURCE_DILRMP,
                })
                print(f"[FIX] Corrected state-level metadata for {path.name}")
        if not sheets:
            print("[SKIP] No Ghaziabad XLSX files found")
        for path in sheets:
            if path.name in names:
                print(f"[SKIP] Already indexed: {path.name}")
                continue
            if path.stat().st_size > 15 * 1024 * 1024:
                print(f"[SKIP] Workbook exceeds 15 MB upload limit: {path.name}")
                continue
            with path.open("rb") as handle:
                job = request(
                    client, "POST", "/documents/jobs",
                    files={"file": (path.name, handle,
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    data={"title": f"DILRMP Uttar Pradesh: {path.stem}",
                          "state": "Uttar Pradesh", "district": "",
                          "source_url": SOURCE_DILRMP},
                )
            job_id = job["job_id"]
            print(f"[WAIT] Indexing {path.name}...")
            deadline = time.monotonic() + 900
            while True:
                status = request(client, "GET", f"/documents/jobs/{job_id}")
                if status["status"] == "completed":
                    print(f"[OK] Indexed: {path.name} (document {status['document_id']})")
                    names.add(path.name)
                    break
                if status["status"] == "failed":
                    print(f"[ERROR] Indexing {path.name}: {status['error']}")
                    break
                if time.monotonic() > deadline:
                    print(f"[WAIT] Still processing {path.name}; check the app's upload jobs.")
                    break
                time.sleep(5)
    print("Import pass complete. Verify document citations and class areas against the originals.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
