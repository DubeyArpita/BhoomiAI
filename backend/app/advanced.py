"""Advanced research tools for an evidence-auditable local BhoomiAI prototype.

No automated claims about the entire literature or external data licensing.
"""
from __future__ import annotations

import csv
import io
import math
from collections import defaultdict

import psycopg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .platform import conn, current_user, require_admin, audit

router = APIRouter(prefix="/advanced", tags=["Advanced Research"])
CSV_COLUMNS = (
    "state", "district", "year", "indicator", "value",
    "unit", "source_url", "dataset_name",
)
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 1000


def parse_indicator_csv(content: bytes):
    """Strict, atomic, provenance-required CSV validation before any inserts."""
    try:
        decoded = content.decode("utf-8-sig")
        table = csv.DictReader(io.StringIO(decoded, newline=""))
    except UnicodeError as exc:
        raise ValueError("CSV must use UTF-8.") from exc
    if not table.fieldnames or set(table.fieldnames) != set(CSV_COLUMNS):
        raise ValueError("CSV columns must be exactly: " + ", ".join(CSV_COLUMNS))
    result = []
    for number, row in enumerate(table, 2):
        if number > MAX_CSV_ROWS + 1:
            raise ValueError(f"Maximum {MAX_CSV_ROWS} data rows per import.")
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Line {number}: unexpected or missing CSV fields.")
        values = {key: row[key].strip() for key in CSV_COLUMNS}
        if not all(values.values()):
            raise ValueError(f"Line {number}: all fields including provenance are required.")
        if any(len(values[k]) > limit for k,limit in (
            ("state",100),("district",100),("indicator",120),
            ("unit",50),("source_url",1000),("dataset_name",200))):
            raise ValueError(f"Line {number}: field exceeds allowed length.")
        if not values["source_url"].startswith(("https://","http://")):
            raise ValueError(f"Line {number}: source_url must be an http(s) URL.")
        try:
            year = int(values["year"])
            value = float(values["value"])
        except ValueError as exc:
            raise ValueError(f"Line {number}: invalid year or numeric value.") from exc
        if not (1990 <= year <= 2100) or not math.isfinite(value):
            raise ValueError(f"Line {number}: year or numeric value out of range.")
        result.append(tuple(
            year if key=="year" else value if key=="value" else values[key]
            for key in CSV_COLUMNS
        ))
    if not result:
        raise ValueError("CSV has no data rows.")
    return result


@router.post("/indicators/import-csv", status_code=201)
async def import_sourced_indicators(
    file: UploadFile = File(...), user=Depends(require_admin),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, "Upload a UTF-8 .csv file.")
    payload=await file.read(MAX_CSV_BYTES+1)
    if len(payload)>MAX_CSV_BYTES:
        raise HTTPException(413,"CSV must not exceed 2 MB.")
    try:
        records=parse_indicator_csv(payload)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    # One transaction; an error never leaves a half-imported dataset.
    with conn() as db:
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO land_indicators(
                    state,district,year,indicator,value,unit,source_url,
                    dataset_name,entered_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(*row,user["id"]) for row in records],
            )
        audit(db,user["id"],"bulk_import_sourced_indicators",len(records))
    return {"imported":len(records),"notice":"Only local user-supplied records; original data and licences are not independently verified."}


@router.get("/evidence-links/{document_id}")
def candidate_evidence_links(
    document_id: int, limit: int = 6, user=Depends(current_user),
):
    """Nearest cross-document excerpts as candidate links, not verified agreement."""
    if not 1 <= limit <= 12:
        raise HTTPException(422,"limit must be between 1 and 12.")
    with conn() as db:
        source=db.execute(
            "SELECT id,COALESCE(title,filename),source_url FROM documents WHERE id=%s",
            (document_id,),
        ).fetchone()
        if not source:
            raise HTTPException(404,"Source document not found.")
        vectors=db.execute(
            "SELECT id,embedding,content,page_number FROM chunks "
            "WHERE document_id=%s ORDER BY id LIMIT 3",(document_id,),
        ).fetchall()
        if not vectors:
            return {"document":{"id":source[0],"title":source[1]},"links":[],
                    "warning":"Document has no indexed excerpts."}
        candidates={}
        for chunk_id,vector,content,page in vectors:
            rows=db.execute(
                """SELECT d.id,COALESCE(d.title,d.filename),d.source_url,
                   c.id,c.page_number,c.content,
                   1-(c.embedding <=> %s::vector) similarity
                   FROM chunks c JOIN documents d ON d.id=c.document_id
                   WHERE d.id<>%s
                   ORDER BY c.embedding <=> %s::vector LIMIT %s""",
                (str(vector),document_id,str(vector),limit*3),
            ).fetchall()
            for r in rows:
                other_id=r[0]
                if other_id not in candidates or float(r[6])>candidates[other_id]["similarity"]:
                    candidates[other_id]={
                        "document_id":other_id,"title":r[1],"source_url":r[2],
                        "source_chunk_id":chunk_id,"source_page":page,
                        "source_excerpt":content[:700],"target_chunk_id":r[3],
                        "target_page":r[4],"target_excerpt":r[5][:700],
                        "similarity":round(float(r[6]),4),
                        "relation":"semantically_similar_candidate",
                    }
    links=sorted(candidates.values(),key=lambda x:x["similarity"],reverse=True)[:limit]
    return {"document":{"id":source[0],"title":source[1],"source_url":source[2]},
            "links":links,
            "warning":"Similarity is not evidence of agreement, citation, causation or scientific validity. Review both original sources."}


class EvidenceCoverageQuery(BaseModel):
    states: list[str] = Field(min_length=1,max_length=8)
    topics: list[str] = Field(min_length=1,max_length=12)
    minimum_similarity:float=Field(default=.48,ge=.2,le=.95)


@router.post("/coverage-evidence")
def coverage_with_provenance(body:EvidenceCoverageQuery,user=Depends(current_user)):
    """Expose top excerpts behind each indexed-corpus coverage cell."""
    from .main import model,vector_literal
    cells=[]
    for state in body.states:
        region=state.strip()
        if not region or len(region)>100:
            raise HTTPException(422,"Every state name must contain 1-100 characters.")
        for topic in body.topics:
            topic=topic.strip()
            if len(topic)<2 or len(topic)>160:
                raise HTTPException(422,"Each topic must contain 2-160 characters.")
            vector=vector_literal(model().encode(
                "Land governance research: "+topic,normalize_embeddings=True))
            with conn() as db:
                rows=db.execute(
                    """SELECT d.id,COALESCE(d.title,d.filename),d.source_url,
                       c.id,c.page_number,c.content,
                       1-(c.embedding <=> %s::vector) similarity
                       FROM chunks c JOIN documents d ON d.id=c.document_id
                       WHERE d.state ILIKE %s
                         AND 1-(c.embedding <=> %s::vector) >= %s
                       ORDER BY similarity DESC LIMIT 100""",
                    (vector,region,vector,body.minimum_similarity),
                ).fetchall()
            by_doc={}
            for r in rows:
                if r[0] not in by_doc:
                    by_doc[r[0]]={
                        "document_id":r[0],"title":r[1],"source_url":r[2],
                        "chunk_id":r[3],"page":r[4],"excerpt":r[5][:700],
                        "similarity":round(float(r[6]),4),
                    }
            cells.append({"state":region,"topic":topic,
                          "matching_indexed_documents":len(by_doc),
                          "evidence":list(by_doc.values())[:5]})
    return {"results":cells,"notice":"Only documents indexed locally and manually tagged to the region. Empty cells are collection gaps, NOT proven gaps in published research."}


@router.get("/public-source-registry")
def source_registry(user=Depends(current_user)):
    """Discovery links, not an automated connector or a claim of download rights."""
    return [
        {"name":"Department of Land Resources","url":"https://dolr.gov.in/",
         "category":"Land administration reports","access":"Check document-specific reuse conditions."},
        {"name":"India Open Government Data","url":"https://www.data.gov.in/",
         "category":"Public statistical datasets","access":"Check each dataset licence and API requirements."},
        {"name":"Copernicus Data Space","url":"https://dataspace.copernicus.eu/",
         "category":"Satellite data catalogue","access":"Registration and dataset terms may apply."},
        {"name":"ISRO Bhuvan","url":"https://bhuvan.nrsc.gov.in/",
         "category":"Indian geospatial reference","access":"Availability and reuse vary by layer."},
    ]
