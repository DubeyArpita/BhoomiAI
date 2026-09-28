"""Lightweight read-only hosted demo for BhoomiAI.

This keeps the full local application unchanged while allowing a free Render
deployment with the committed Ghaziabad/DILRMP datasets. Heavy local Ollama and
pgvector indexing are intentionally not started on the free hosted demo.
"""
from __future__ import annotations
import io, json, os, re, uuid
from pathlib import Path
from typing import Any
import fitz
import numpy as np
import rasterio
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, transform_geom
from PIL import Image

from app.dilrmp import data_for_district, locate, read_report, clean_district

ROOT=Path(__file__).resolve().parents[1]
BOUNDARY=ROOT/"datasets/gis/boundaries/uttar_pradesh/Ghaziabad_Boundary.geojson"
RASTER=ROOT/"datasets/satellite/esa_worldcover/2021/original/Ghaziabad_WorldCover_2021.tif.tif"
REPORT=ROOT/"datasets/government_reports/DoLR_Annual_Report_2024_25.pdf"
SOURCE_URL="https://dolr.gov.in/en/annual-reports/"
DILRMP_URL="https://dilrmp.gov.in/reports/download-progress-report"
BOUNDARY_ID=uuid.UUID("11111111-1111-4111-8111-111111111111")
SCENE_ID=uuid.UUID("22222222-2222-4222-8222-222222222222")

app=FastAPI(title="BhoomiAI Hosted Demo",version="1.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

@app.get("/health")
def health(): return {"status":"ok","mode":"hosted-read-only-demo"}

def boundary_data():
    return json.loads(BOUNDARY.read_text(encoding="utf-8"))

def xy_only(node):
    if isinstance(node,list):
        if len(node)>=2 and all(isinstance(v,(int,float)) for v in node[:2]):
            return node[:2]
        return [xy_only(x) for x in node]
    return node

def clean_geojson(data):
    out={"type":"FeatureCollection","name":data.get("name","Ghaziabad")}
    feats=[]
    for f in data.get("features",[]):
        g=dict(f.get("geometry") or {})
        g["coordinates"]=xy_only(g.get("coordinates"))
        feats.append({"type":"Feature","properties":f.get("properties",{}),"geometry":g})
    out["features"]=feats
    return out

# ---------- Documents / lightweight evidence retrieval ----------
@app.get("/documents")
def documents(q:str="",state:str="",district:str=""):
    if q and q.lower() not in "department of land resources annual report 2024-25":
        return []
    return [{"id":1,"filename":"DoLR_Annual_Report_2024_25.pdf",
             "title":"Department of Land Resources Annual Report 2024-25",
             "state":"","district":"","source_url":SOURCE_URL,"chunks":1}]

class ChatIn(BaseModel):
    question:str
    state:str=""
    district:str=""

def page_texts():
    if not REPORT.exists(): return []
    pdf=fitz.open(REPORT)
    try: return [(i+1,pdf[i].get_text(sort=True)) for i in range(len(pdf))]
    finally: pdf.close()

@app.post("/chat")
def chat(body:ChatIn):
    tokens=[t for t in re.findall(r"[a-zA-Z]{4,}",body.question.lower())
            if t not in {"what","which","where","when","with","from","that","this","about","major"}]
    scored=[]
    for page,text in page_texts():
        low=text.lower()
        score=sum(low.count(t) for t in tokens)
        if score:
            scored.append((score,page,re.sub(r"\s+"," ",text).strip()))
    scored.sort(reverse=True)
    chosen=scored[:3]
    if not chosen:
        chosen=[(0,p,t) for p,t in page_texts()[:2]]
    excerpts=[]
    for _,page,text in chosen:
        if tokens:
            pos=min([text.lower().find(t) for t in tokens if text.lower().find(t)>=0] or [0])
        else: pos=0
        start=max(0,pos-240); excerpt=text[start:start+900]
        excerpts.append({"chunk_id":page,"ref":len(excerpts)+1,
                         "title":"Department of Land Resources Annual Report 2024-25",
                         "filename":"DoLR_Annual_Report_2024_25.pdf","page":page,
                         "source_url":SOURCE_URL,"excerpt":excerpt})
    answer=("Hosted demo retrieval found the following relevant evidence in the official "
            "Department of Land Resources Annual Report. Review the cited passages below "
            "for the exact wording and context. The full local BhoomiAI prototype uses "
            "semantic embeddings and a local LLM; this free hosted version uses lightweight "
            "evidence retrieval to stay within free hosting limits.")
    return {"answer":answer,"sources":excerpts}

@app.post("/documents/jobs",status_code=503)
def no_upload(): raise HTTPException(503,"Uploads are disabled in the public hosted demo.")
@app.get("/documents/jobs/{job_id}",status_code=503)
def no_job(job_id:str): raise HTTPException(503,"Uploads are disabled in the public hosted demo.")
@app.delete("/documents/{document_id}",status_code=503)
def no_delete(document_id:int): raise HTTPException(503,"Deletion is disabled in the public hosted demo.")

# ---------- GIS / raster ----------
@app.get("/gis/layers")
def gis_layers():
    return [{"id":str(BOUNDARY_ID),"name":"Ghaziabad district boundary (Survey of India)",
             "source_url":"https://onlinemaps.surveyofindia.gov.in/","licence":"Official public boundary source",
             "description":"Ghaziabad district boundary used for the SIH proof of concept.",
             "created_at":"2026-09-01T00:00:00+00:00","feature_count":1}]

@app.get("/gis/layers/{layer_id}/features")
def gis_features(layer_id:uuid.UUID,limit:int=Query(1000,ge=1,le=5000)):
    if layer_id!=BOUNDARY_ID: raise HTTPException(404,"Layer not found")
    return clean_geojson(boundary_data())

@app.get("/gis/layers/{layer_id}/landuse-stats")
def landuse(layer_id:uuid.UUID):
    if layer_id!=BOUNDARY_ID: raise HTTPException(404,"Layer not found")
    return {"layer_id":str(layer_id),"name":"Ghaziabad district boundary (Survey of India)",
            "source_url":"https://onlinemaps.surveyofindia.gov.in/","licence":"Official public boundary source",
            "categories":[],"warning":"This boundary layer has no land_use attribute. Use ESA WorldCover statistics instead."}

@app.get("/raster/scenes")
def raster_scenes():
    if not RASTER.exists(): return []
    with rasterio.open(RASTER) as ds:
        bounds=transform_bounds(ds.crs,"EPSG:4326",*ds.bounds,densify_pts=21)
        return [{"id":str(SCENE_ID),"title":"ESA WorldCover 2021 - Ghaziabad (annual composite)",
                 "capture_date":"2021-01-01","platform":"ESA WorldCover 2021",
                 "source_url":"https://esa-worldcover.org/","licence":"CC BY 4.0",
                 "bounds":list(bounds),"bands":ds.count,"width":ds.width,"height":ds.height}]

PALETTE={10:(0,100,0),20:(255,187,34),30:(255,255,76),40:(240,150,255),
         50:(250,0,0),60:(180,180,180),70:(240,240,240),80:(0,100,200),
         90:(0,150,160),95:(0,207,117),100:(250,230,160)}
CLASSES={10:"Tree cover",20:"Shrubland",30:"Grassland",40:"Cropland",50:"Built-up",
         60:"Bare / sparse vegetation",70:"Snow and ice",80:"Permanent water bodies",
         90:"Herbaceous wetland",95:"Mangroves",100:"Moss and lichen"}

@app.get("/raster/scenes/{scene_id}/preview")
def raster_preview(scene_id:uuid.UUID):
    if scene_id!=SCENE_ID or not RASTER.exists(): raise HTTPException(404,"Raster not found")
    with rasterio.open(RASTER) as ds:
        factor=max(1,int(np.ceil(max(ds.width,ds.height)/900)))
        shape=(max(1,ds.height//factor),max(1,ds.width//factor))
        arr=ds.read(1,out_shape=shape,resampling=rasterio.enums.Resampling.nearest)
        mask=ds.read_masks(1,out_shape=shape,resampling=rasterio.enums.Resampling.nearest)>0
    rgba=np.zeros((*arr.shape,4),dtype=np.uint8)
    for code,rgb in PALETTE.items():
        sel=mask&(arr==code); rgba[sel,:3]=rgb; rgba[sel,3]=255
    out=io.BytesIO(); Image.fromarray(rgba,"RGBA").save(out,format="PNG")
    return Response(out.getvalue(),media_type="image/png")

@app.get("/raster/scenes/{scene_id}/landcover-stats")
def raster_stats(scene_id:uuid.UUID,boundary_layer_id:uuid.UUID):
    if scene_id!=SCENE_ID or boundary_layer_id!=BOUNDARY_ID: raise HTTPException(404,"Scene or boundary not found")
    data=clean_geojson(boundary_data()); geoms=[f["geometry"] for f in data["features"]]
    with rasterio.open(RASTER) as ds:
        transformed=[transform_geom("EPSG:4326",ds.crs,g) for g in geoms]
        xs=[];ys=[]
        def pts(n):
            if isinstance(n,list) and len(n)>=2 and isinstance(n[0],(int,float)):
                xs.append(n[0]);ys.append(n[1])
            elif isinstance(n,list):
                for x in n: pts(x)
        for g in transformed: pts(g["coordinates"])
        win=from_bounds(min(xs),min(ys),max(xs),max(ys),ds.transform).round_offsets().round_lengths()
        arr=ds.read(1,window=win); valid=ds.read_masks(1,window=win)>0
        inside=geometry_mask(transformed,out_shape=arr.shape,transform=ds.window_transform(win),invert=True)
        included=valid&inside&(arr!=0)
        vals,cnts=np.unique(arr[included],return_counts=True)
        counts={int(v):int(c) for v,c in zip(vals,cnts)}
        pixel_ha=abs(ds.transform.a*ds.transform.e-ds.transform.b*ds.transform.d)/10000.0
    total=sum(counts.values())
    cats=[{"code":c,"name":CLASSES.get(c,f"Unknown code {c}"),"pixels":n,
           "area_ha":round(n*pixel_ha,2),"percentage":round(n/total*100,2) if total else 0}
          for c,n in sorted(counts.items())]
    return {"scene_id":str(scene_id),"boundary_layer_id":str(boundary_layer_id),
            "scene_title":"ESA WorldCover 2021 - Ghaziabad (annual composite)",
            "boundary_name":"Ghaziabad district boundary (Survey of India)",
            "source_url":"https://esa-worldcover.org/","product":"ESA WorldCover categorical map",
            "analysed_pixels":total,"analysed_area_ha":round(total*pixel_ha,2),"categories":cats,
            "limitations":"Approximate raster pixel counts within the selected boundary. WorldCover is land cover, not a cadastral legal record."}

# ---------- DILRMP ----------
@app.get("/dilrmp/districts")
def districts():
    path=locate("mrr") or locate("clr")
    if not path: return {"state":"Uttar Pradesh","districts":["GHAZIABAD","AGRA"]}
    key="mrr" if "Modern Record Room" in path.name else "clr"
    _,records=read_report(key,str(path),path.stat().st_mtime_ns)
    return {"state":"Uttar Pradesh","districts":sorted(records)}

@app.get("/dilrmp/district")
def district(district:str="Ghaziabad"):
    return data_for_district(district)

# ---------- Research & Policy Hub ----------
@app.get("/platform/projects")
def projects(): return []
@app.get("/platform/indicators")
def indicators(): return []
@app.get("/platform/challenges")
def challenges(): return []
@app.get("/platform/users")
def users(): return []
@app.get("/platform/insights")
def insights():
    return {"total_indexed_documents":1,"by_region":[{"state":"National","district":"—","count":1}]}
@app.get("/platform/graph")
def graph():
    return {"nodes":[{"id":"doc:1","label":"DoLR Annual Report 2024-25","type":"document"},
                     {"id":"region:india","label":"India","type":"region"}],
            "edges":[{"source":"doc:1","target":"region:india","relation":"covers_region"}]}
class Scenario(BaseModel):
    total_area_ha:float=Field(ge=0)
    baseline_conversion_ha:float=Field(ge=0)
    proposed_restriction_fraction:float=Field(ge=0,le=1)
    assumed_compliance_fraction:float=Field(ge=0,le=1)
@app.post("/platform/scenarios")
def scenario(x:Scenario):
    avoided=x.baseline_conversion_ha*x.proposed_restriction_fraction*x.assumed_compliance_fraction
    return {"hypothetical_avoided_conversion_ha":round(avoided,3),
            "hypothetical_conversion_ha":round(max(0,x.baseline_conversion_ha-avoided),3),
            "formula":"baseline × restriction fraction × assumed compliance",
            "warning":"Exploratory arithmetic only; not a prediction or policy-effect estimate.",
            "assumptions":"User-supplied quantities are treated as hypothetical inputs."}

@app.get("/platform/research-coverage")
def coverage(): return {"coverage":[],"warning":"Hosted demo contains one national report."}
@app.get("/platform/recommendations/{document_id}")
def recommendations(document_id:int): return []
@app.post("/platform/{path:path}",status_code=503)
def no_platform_writes(path:str): raise HTTPException(503,"Editing is disabled in the public hosted demo.")

# ---------- Data & Provenance ----------
@app.get("/advanced/data-readiness")
def readiness():
    return {"documents":{"total":1,"missing_source_url":0,"missing_state_tag":1},
            "evidence_notes":{"confirmed":0},"indicator_coverage":[],
            "warning":"Hosted demo reports only the bundled public demonstration sources."}
@app.get("/advanced/provenance-graph")
def provenance():
    return {"nodes":[{"id":"doc:1","label":"DoLR Annual Report 2024-25","type":"document"},
                     {"id":"source:dolr","label":"Department of Land Resources","type":"source"},
                     {"id":"region:india","label":"India","type":"region"}],
            "edges":[{"source":"doc:1","target":"source:dolr","relation":"published_by"},
                     {"source":"doc:1","target":"region:india","relation":"covers_region"}],
            "provenance_policy":"Only explicit source relationships are shown; missing links are not inferred."}
@app.get("/advanced/indicators/template")
def template():
    data="state,district,year,indicator,value,unit,source_url,dataset_name\n"
    return StreamingResponse(io.BytesIO(data.encode()),media_type="text/csv",
        headers={"Content-Disposition":"attachment; filename=indicator_template.csv"})
@app.get("/advanced/indicators/export")
def export():
    data="state,district,year,indicator,value,unit,source_url,dataset_name\n"
    return StreamingResponse(io.BytesIO(data.encode()),media_type="text/csv",
        headers={"Content-Disposition":"attachment; filename=land_indicators.csv"})
@app.get("/advanced/indicators/trends")
def trends(state:str,district:str,indicator:str):
    return {"series":[],"changes":[],"warning":"No manually entered historical indicator series is bundled in the hosted demo."}
@app.post("/advanced/indicators/import-csv",status_code=503)
def no_csv(): raise HTTPException(503,"CSV import is disabled in the public hosted demo.")
