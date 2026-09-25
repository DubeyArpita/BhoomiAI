"""Provenance-focused analysis and batch import for BhoomiAI's local prototype.

All graph relations are explicitly recorded, not automatically inferred facts.
Descriptive time trends are not causal policy simulations.
"""
from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from urllib.parse import urlsplit

import psycopg
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from .platform import conn, current_user, require_admin, audit

router = APIRouter(prefix="/advanced", tags=["Provenance and Data Quality"])

COLUMNS = (
    "state", "district", "year", "indicator", "value",
    "unit", "source_url", "dataset_name"
)
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 1000


def parse_indicator_csv(data: bytes):
    """Validate user-supplied CSV without silently repairing ambiguous values."""
    try:
        raw = data.decode("utf-8-sig")
        rows = csv.DictReader(io.StringIO(raw, newline=""))
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("CSV must be valid UTF-8.") from exc
    if not rows.fieldnames or any(col not in rows.fieldnames for col in COLUMNS):
        raise ValueError("CSV header must contain: " + ", ".join(COLUMNS))
    if len(rows.fieldnames) != len(set(rows.fieldnames)):
        raise ValueError("Duplicate CSV header fields are not allowed.")
    cleaned = []
    try:
        for index, entry in enumerate(rows, start=2):
            if len(cleaned) >= MAX_CSV_ROWS:
                raise ValueError(f"Maximum {MAX_CSV_ROWS} indicator rows.")
            if not entry or None in entry:
                raise ValueError(f"Row {index}: unexpected extra columns.")
            item = {key: (entry.get(key) or "").strip() for key in COLUMNS}
            for key in ("state", "district", "indicator", "unit", "source_url", "dataset_name"):
                if not item[key]:
                    raise ValueError(f"Row {index}: {key} cannot be empty.")
            if any(len(item[k]) > width for k, width in (
                ("state", 100), ("district", 100), ("indicator", 120),
                ("unit", 50), ("source_url", 1000), ("dataset_name", 200)
            )):
                raise ValueError(f"Row {index}: field exceeds maximum length.")
            try:
                year = int(item["year"])
                value = float(item["value"])
            except ValueError as exc:
                raise ValueError(f"Row {index}: invalid numeric year/value.") from exc
            if not 1990 <= year <= 2100 or not math.isfinite(value):
                raise ValueError(f"Row {index}: year out of range or value not finite.")
            url = urlsplit(item["source_url"])
            if url.scheme not in ("https", "http") or not url.netloc:
                raise ValueError(f"Row {index}: source_url must be an absolute HTTP(S) URL.")
            cleaned.append((
                item["state"], item["district"], year, item["indicator"],
                value, item["unit"], item["source_url"], item["dataset_name"]
            ))
    except csv.Error as exc:
        raise ValueError("Malformed CSV: " + str(exc)) from exc
    if not cleaned:
        raise ValueError("CSV must contain at least one indicator.")
    return cleaned


def descriptive_trend(records):
    """Return deltas only for a unique, unit-consistent observation per year."""
    if not records:
        return {"series": [], "changes": [], "warning": "No matching observations."}
    grouped = defaultdict(list)
    for entry in records:
        grouped[entry["year"]].append(entry)
    ambiguous = sorted(year for year, values in grouped.items() if len(values) != 1)
    units = {entry["unit"] for entry in records}
    series = sorted(records, key=lambda x: x["year"])
    if ambiguous or len(units) != 1:
        return {
            "series": series, "changes": [], "ambiguous_years": ambiguous,
            "warning": "No change calculated: repeated observations or mixed units. "
                       "Select one comparable original dataset and remove duplicates."
        }
    changes = []
    for earlier, later in zip(series, series[1:]):
        delta = later["value"] - earlier["value"]
        pct = None if earlier["value"] == 0 else 100 * delta / abs(earlier["value"])
        changes.append({
            "from_year": earlier["year"], "to_year": later["year"],
            "absolute_change": round(delta, 5),
            "percentage_change": round(pct, 3) if pct is not None else None,
            "unit": earlier["unit"],
        })
    return {
        "series": series, "changes": changes, "ambiguous_years": [],
        "warning": "Descriptive observations only; source comparability is unverified. "
                   "Changes do not establish policy impact or causality."
    }


@router.post("/indicators/import-csv", status_code=201)
async def import_indicators(file: UploadFile = File(...), user=Depends(require_admin)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, "Choose a .csv file.")
    data = await file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV exceeds 2 MB.")
    try:
        rows = parse_indicator_csv(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # All records are inserted in a single database transaction.
    with conn() as db:
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO land_indicators
                   (state,district,year,indicator,value,unit,source_url,dataset_name,entered_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(*entry, user["id"]) for entry in rows]
            )
        audit(db, user["id"], "bulk_import_indicators", f"{len(rows)} rows")
    return {"imported": len(rows), "interpretation": "User-entered source-attributed data; original source is not independently verified."}


@router.get("/indicators/template")
def indicator_template(user=Depends(current_user)):
    content = ",".join(COLUMNS) + "\r\n"
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=indicator_template.csv"}
    )


@router.get("/indicators/export")
def export_indicators(user=Depends(current_user)):
    with conn() as db:
        rows = db.execute(
            """SELECT state,district,year,indicator,value,unit,source_url,dataset_name
               FROM land_indicators ORDER BY state,district,indicator,year,id
               LIMIT 10000"""
        ).fetchall()
    handle = io.StringIO()
    writer = csv.writer(handle)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return StreamingResponse(
        io.BytesIO(handle.getvalue().encode("utf-8-sig")), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=land_indicators.csv"}
    )


@router.get("/indicators/trends")
def indicator_trends(
    state: str = Query(min_length=2),
    district: str = Query(min_length=2),
    indicator: str = Query(min_length=2),
    user=Depends(current_user),
):
    with conn() as db:
        rows = db.execute(
            """SELECT year,value,unit,source_url,dataset_name FROM land_indicators
               WHERE state ILIKE %s AND district ILIKE %s AND indicator ILIKE %s
               ORDER BY year,id LIMIT 1000""",
            (state, district, indicator)
        ).fetchall()
    records = [
        {"year": row[0], "value": row[1], "unit": row[2],
         "source_url": row[3], "dataset_name": row[4]} for row in rows
    ]
    return {
        "query": {"state": state, "district": district, "indicator": indicator},
        **descriptive_trend(records)
    }


@router.get("/data-readiness")
def data_readiness(user=Depends(current_user)):
    with conn() as db:
        docs = db.execute(
            """SELECT COUNT(*), COUNT(*) FILTER (WHERE COALESCE(source_url,'')=''),
               COUNT(*) FILTER (WHERE COALESCE(state,'')=''),
               COUNT(*) FILTER (WHERE COALESCE(district,'')='')
               FROM documents"""
        ).fetchone()
        regions = db.execute(
            """SELECT state,district,COUNT(DISTINCT year),
                      COUNT(DISTINCT indicator), COUNT(*)
               FROM land_indicators GROUP BY state,district ORDER BY COUNT(*) DESC LIMIT 100"""
        ).fetchall()
        projects = db.execute(
            """SELECT COUNT(*),COUNT(*) FILTER(WHERE review_status='confirmed'),
                      COUNT(*) FILTER(WHERE review_status='pending')
               FROM research_notes"""
        ).fetchone()
    return {
        "documents": {"total": docs[0], "missing_source_url": docs[1],
                      "missing_state_tag": docs[2], "missing_district_tag": docs[3]},
        "indicator_coverage": [
            {"state": row[0], "district": row[1], "years": row[2],
             "indicators": row[3], "observations": row[4]} for row in regions
        ],
        "evidence_notes": {"total": projects[0], "confirmed": projects[1],
                           "pending": projects[2]},
        "warning": "Coverage is limited to uploaded sources. Metadata is entered by users; "
                   "counts neither certify authenticity nor establish real research gaps."
    }


@router.get("/provenance-graph")
def provenance_graph(user=Depends(current_user)):
    """Explicit, traceable graph with source URLs and scoped collaboration evidence."""
    nodes, edges = {}, []
    def add_node(node_id, label, category, **data):
        nodes[node_id] = {"id": node_id, "label": label, "type": category, **data}
    def link(source, target, relation, evidence_id=None):
        edges.append({"source": source, "target": target, "relation": relation,
                      "evidence_id": evidence_id})
    with conn() as db:
        documents = db.execute(
            """SELECT id,COALESCE(NULLIF(title,''),filename),state,district,source_url
               FROM documents ORDER BY id LIMIT 200"""
        ).fetchall()
        for doc_id, title, state, district, url in documents:
            identifier = f"doc:{doc_id}"
            add_node(identifier, title, "document", source_url=url or None)
            if url:
                sid = "source:" + url
                add_node(sid, url, "source", source_url=url)
                link(identifier, sid, "source_metadata")
            if state:
                tag = "state:" + state.casefold()
                add_node(tag, state, "state")
                link(identifier, tag, "manually_tagged")
            if district:
                tag = "district:" + (state or "").casefold() + ":" + district.casefold()
                add_node(tag, district, "district")
                link(identifier, tag, "manually_tagged")
        project_rows = db.execute(
            """SELECT id,title FROM research_projects
               WHERE %s='admin' OR created_by=%s OR EXISTS (
                 SELECT 1 FROM project_members m
                 WHERE m.project_id=research_projects.id AND m.user_id=%s)
               LIMIT 100""",
            (user["role"], user["id"], user["id"])
        ).fetchall()
        for project_id, title in project_rows:
            project = f"project:{project_id}"
            add_node(project, title, "project")
            notes = db.execute(
                """SELECT id,document_id,source_url,review_status
                   FROM research_notes WHERE project_id=%s LIMIT 250""",
                (project_id,)
            ).fetchall()
            for nid, doc_id, url, status in notes:
                note = f"note:{nid}"
                add_node(note, f"Evidence note {nid} ({status})", "research_note",
                         review_status=status)
                link(project, note, "project_note", nid)
                if doc_id and f"doc:{doc_id}" in nodes:
                    link(note, f"doc:{doc_id}", "user_linked_document", nid)
                if url:
                    sid = "source:" + url
                    add_node(sid, url, "source", source_url=url)
                    link(note, sid, "note_source_url", nid)
    return {
        "nodes": list(nodes.values()), "edges": edges,
        "provenance_policy": "Only stored metadata and explicit research-note links. "
                             "Note review status is shown; source authenticity is not verified. "
                             "No inferred biomedical, administrative or causal relationship."
    }
