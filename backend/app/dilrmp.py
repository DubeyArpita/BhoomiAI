"""Source-traceable district snapshots from the committed UP DILRMP XLSX reports.

No guessed dates, district-level filtering of state totals, or interpolation.
The original downloaded workbooks contain all UP districts, even when stored
in the 'ghaziabad' folder. Read the state_reports copies as primary sources.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from openpyxl import load_workbook

from .platform import current_user

router = APIRouter(prefix="/dilrmp", tags=["Official DILRMP District Data"])
ROOT = Path(__file__).resolve().parents[2]
PRIMARY = ROOT / "datasets/dilrmp/Uttar Pradesh/state_reports"
FALLBACK = ROOT / "datasets/dilrmp/Uttar Pradesh/ghaziabad"
SOURCE_URL = "https://dilrmp.gov.in/reports/download-progress-report"

# Zero ambiguity: column indices are 1-based and checked against the exact
# three-row merged header layout in the downloaded Department of Land
# Resources Excel files. Number and percent columns are intentionally
# distinct, as are different denominators in the map-digitization sheet.
REPORTS = {
    "clr": {
        "filename": "Computerization of Land Records (CLR).xlsx",
        "title": "Computerization of Land Records",
        "sheet_title": "Computerization of Land Records (CLR)",
        "header_row": 7,
        "headers": {2: "District Name", 3: "Total Tehsils", 4: "Total Villages",
                    5: "No. of RoR", 10: "No. of Villages Where CLR Completed"},
        "fields": (
            ("total_tehsils", "Total tehsils", 3, "count"),
            ("total_villages", "Total villages", 4, "count"),
            ("ror_total", "RoR — total", 5, "count"),
            ("ror_computerized", "RoR — computerized", 6, "count"),
            ("ror_computerized_pct", "RoR — computerized", 7, "%"),
            ("ror_linked_cadastral", "RoR linked with cadastral maps", 8, "count"),
            ("ror_linked_cadastral_pct", "RoR linked with cadastral maps", 9, "%"),
            ("villages_clr_completed", "Villages with CLR completed", 10, "count"),
            ("villages_clr_completed_pct", "Villages with CLR completed", 11, "%"),
            ("ror_available_online", "RoR downloadable online", 17, "Yes/No"),
            ("digitally_signed_ror", "Digitally signed RoR online", 18, "Yes/No"),
            ("online_mutation_application", "Online mutation application", 20, "Yes/No"),
        ),
    },
    "maps": {
        "filename": "Map Digitization.xlsx",
        "title": "Map Digitization",
        "header_row": 7,
        "headers": {2: "District Name", 4: "No. of Cadastral Maps / FMBs / Tippans",
                    21: "No. of Villages"},
        "fields": (
            ("total_cadastral_maps", "Cadastral maps — total", 4, "count"),
            ("digitized_cadastral_maps", "Cadastral maps — digitized", 7, "count"),
            ("digitized_cadastral_maps_pct", "Cadastral maps digitized (of total)", 8, "%"),
            ("total_map_documents", "Maps + FMBs + Tippans — total", 16, "count"),
            ("digitized_map_documents", "Maps + FMBs + Tippans — digitized", 17, "count"),
            ("digitized_map_documents_pct", "Maps + FMBs + Tippans digitized", 18, "%"),
            ("georeferenced_map_documents", "Maps + FMBs + Tippans — geo-referenced", 19, "count"),
            ("georeferenced_map_documents_pct", "Maps + FMBs + Tippans geo-referenced", 20, "%"),
            ("total_villages", "Villages — total", 21, "count"),
            ("villages_maps_linked_ror", "Villages: maps linked with RoR", 22, "count"),
            ("villages_maps_linked_ror_pct", "Villages: maps linked with RoR", 23, "%"),
            ("villages_maps_georeferenced", "Villages: maps geo-referenced", 24, "count"),
            ("villages_maps_georeferenced_pct", "Villages: maps geo-referenced", 25, "%"),
            ("villages_ulpin_assigned", "Villages with ULPIN assigned", 26, "count"),
            ("villages_ulpin_assigned_pct", "Villages with ULPIN assigned", 27, "%"),
            ("total_land_parcels", "Land parcels — total", 28, "count"),
            ("georeferenced_land_parcels", "Land parcels — geo-referenced", 29, "count"),
            ("georeferenced_land_parcels_pct", "Land parcels geo-referenced", 30, "%"),
            ("ulpin_land_parcels", "Land parcels assigned ULPIN", 31, "count"),
            ("ulpin_land_parcels_pct", "Land parcels assigned ULPIN", 32, "%"),
        ),
    },
    "mrr": {
        "filename": "Modern Record Room (MRR).xlsx",
        "title": "Modern Record Room",
        "sheet_title": "Modern Record Room (MRR)",
        "header_row": 7,
        "headers": {2: "District Name", 3: "Total Tehsils",
                    4: "MRR Sanctioned", 6: "MRR Completed (Out of Total)"},
        "fields": (
            ("total_tehsils", "Total tehsils", 3, "count"),
            ("mrr_sanctioned", "Modern record rooms sanctioned", 4, "count"),
            ("mrr_sanctioned_pct", "MRR sanctioned (of total)", 5, "%"),
            ("mrr_completed", "Modern record rooms completed", 6, "count"),
            ("mrr_completed_pct", "MRR completed (of all tehsils)", 7, "%"),
            ("mrr_completed_sanctioned", "MRR completed (of sanctioned)", 8, "count"),
            ("mrr_completed_sanctioned_pct", "MRR completed (of sanctioned)", 9, "%"),
        ),
    },
    "survey": {
        "filename": "Survey-Re-Survey under NLRMP DILRMP.xlsx",
        "title": "Survey / Re-Survey under NLRMP / DILRMP",
        "header_row": 7,
        "headers": {2: "District Name", 4: "Total Villages",
                    5: "Total Rural Revenue Area (Sq.Km.)",
                    6: "Area Sanctioned for Survey / Re-survey (Sq.Km.)"},
        "fields": (
            ("total_villages", "Total villages", 4, "count"),
            ("rural_revenue_area", "Rural revenue area", 5, "km²"),
            ("survey_area_sanctioned", "Survey/re-survey area sanctioned", 6, "km²"),
            ("villages_drone_flying_completed", "Villages: drone flying completed", 7, "count"),
            ("drone_area_completed", "Drone flying area completed", 8, "km²"),
            ("villages_map_generated", "Villages: Map 1 generated", 9, "count"),
            ("villages_draft_published", "Villages: draft map published", 10, "count"),
            ("villages_final_promulgation", "Villages: final promulgation", 11, "count"),
            ("villages_survey_not_started", "Villages: sanctioned survey not started", 12, "count"),
            ("survey_area_not_started", "Area of sanctioned survey not started", 13, "km²"),
        ),
    },
}


def clean_district(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).upper()


def locate(key):
    spec = REPORTS[key]
    for root in (PRIMARY, FALLBACK):
        path = root / spec["filename"]
        if path.is_file():
            return path
    return None


@lru_cache(maxsize=20)
def read_report(key, path_str, modified_ns):
    """Key by file modification time to avoid stale data after new downloads."""
    spec = REPORTS[key]
    book = load_workbook(path_str, read_only=True, data_only=True)
    try:
        sheet = book.active
        if str(sheet.cell(4, 1).value or "").strip().lower() != spec.get("sheet_title", spec["title"]).lower():
            raise ValueError(f"Unexpected report title in {Path(path_str).name}")
        headers = next(sheet.iter_rows(
            min_row=spec["header_row"], max_row=spec["header_row"], values_only=True
        ))
        for index, expected in spec["headers"].items():
            if str(headers[index - 1] or "").strip() != expected:
                raise ValueError(
                    f"Header drift: {Path(path_str).name} {sheet.title}!{index}, "
                    f"expected {expected!r}; found {headers[index - 1]!r}"
                )
        district_rows = {}
        first_data_row = 10 if key == "clr" else (9 if key in ("mrr", "survey") else 10)
        for row_number, cells in enumerate(
            sheet.iter_rows(min_row=first_data_row, values_only=True), start=first_data_row
        ):
            district = clean_district(cells[1] if len(cells) > 1 else "")
            serial = cells[0] if cells else None
            if not district or not str(serial or "").strip().isdigit():
                continue
            if district in district_rows:
                raise ValueError(f"Duplicate district {district} in {path_str}")
            district_rows[district] = (row_number, tuple(cells))
        if not district_rows:
            raise ValueError("No district rows found in the source worksheet")
        return sheet.title, district_rows
    finally:
        book.close()


def data_for_district(district="Ghaziabad"):
    district_key = clean_district(district)
    result = {"district": district_key.title(), "state": "Uttar Pradesh",
              "reporting_date": None, "date_note": "Download date and report reporting date not verified; values are a single source snapshot.",
              "reports": [], "missing_reports": []}
    for key, spec in REPORTS.items():
        path = locate(key)
        if path is None:
            result["missing_reports"].append(spec["filename"])
            continue
        try:
            sheet_name, rows = read_report(key, str(path), path.stat().st_mtime_ns)
        except (OSError, ValueError, IndexError) as exc:
            result["missing_reports"].append(f"{spec['filename']}: {exc}")
            continue
        if district_key not in rows:
            result["missing_reports"].append(
                f"{spec['filename']}: {district_key} not in source table")
            continue
        line, values = rows[district_key]
        fields = []
        for code, label, column, unit in spec["fields"]:
            raw = values[column - 1] if len(values) >= column else None
            if raw is None or str(raw).strip() in ("", "-", "NA", "N/A"):
                val = None
            elif unit == "Yes/No":
                val = str(raw).strip().upper()
            elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
                val = float(raw) if unit in ("%", "km²") else int(raw)
            else:
                try:
                    numeric = float(str(raw).replace(",", "").strip())
                    val = numeric if unit in ("%", "km²") else int(numeric)
                except ValueError:
                    val = None
            col_letter = sheet_column(column)
            fields.append({"key": code, "label": label, "value": val, "unit": unit,
                           "cell": f"{col_letter}{line}"})
        result["reports"].append({
            "key": key, "title": spec["title"],
            "source_file": path.name,
            "source_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "source_url": SOURCE_URL,
            "sheet": sheet_name, "row": line,
            "dataset_scope": "Uttar Pradesh — one record per district",
            "fields": fields,
        })
    return result


def sheet_column(n):
    letters = ""
    while n:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


@router.get("/districts")
def get_districts(user=Depends(current_user)):
    path = locate("mrr") or locate("clr")
    if not path:
        raise HTTPException(404, "No committed DILRMP source XLSX report found.")
    key = "mrr" if path.name == REPORTS["mrr"]["filename"] else "clr"
    try:
        _, records = read_report(key, str(path), path.stat().st_mtime_ns)
    except (OSError, ValueError, IndexError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"state": "Uttar Pradesh", "districts": sorted(records)}


@router.get("/district")
def get_district(
    district: str = Query(default="Ghaziabad", min_length=2, max_length=100),
    user=Depends(current_user),
):
    payload = data_for_district(district)
    if not payload["reports"]:
        raise HTTPException(404, "No matching district found in the committed DILRMP files.")
    return payload
