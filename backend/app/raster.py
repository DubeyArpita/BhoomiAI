"""Local, evidence-labelled satellite raster ingestion and exploratory vegetation comparison.

No inference of land ownership, policy effectiveness, construction or legal boundaries.
Cloud/snow masks and harmonized multi-sensor analysis are not implemented.
"""
from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

import numpy as np
import rasterio
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import reproject
from .gis import geo_connection

router=APIRouter(prefix="/raster",tags=["Satellite Raster"])
STORE=Path(__file__).resolve().parent.parent / "local_rasters"
MAX_BYTES=40*1024*1024
MAX_PIXELS=25_000_000


def init_raster_database():
    STORE.mkdir(exist_ok=True)
    with geo_connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS raster_scenes(
          id UUID PRIMARY KEY, title TEXT NOT NULL, capture_date DATE NOT NULL,
          platform TEXT NOT NULL, source_url TEXT NOT NULL, licence TEXT NOT NULL,
          local_filename TEXT NOT NULL, srid INTEGER, bounds_wgs84 JSONB NOT NULL,
          band_count INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
          created_at TIMESTAMPTZ DEFAULT NOW())""")


@router.post("/scenes",status_code=201)
async def upload_scene(
    file:UploadFile=File(...), title:str=Form(min_length=2,max_length=200),
    capture_date:str=Form(...), platform:str=Form(...),
    source_url:str=Form(...), licence:str=Form(...),
):
    from datetime import date
    from psycopg.types.json import Jsonb
    try:
        day=date.fromisoformat(capture_date)
    except ValueError as exc:
        raise HTTPException(422,"Capture date must be YYYY-MM-DD") from exc
    if not source_url.startswith(("https://","http://")):
        raise HTTPException(422,"Source URL must identify an original publication.")
    if not file.filename or not file.filename.lower().endswith((".tif",".tiff")):
        raise HTTPException(422,"Only GeoTIFF uploads are supported.")
    content=await file.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:
        raise HTTPException(413,"GeoTIFF exceeds the 40MB prototype limit.")
    sid=uuid.uuid4()
    path=STORE/(str(sid)+".tif")
    try:
        with rasterio.MemoryFile(content) as mem:
            with mem.open() as ds:
                if ds.crs is None:
                    raise HTTPException(422,"GeoTIFF must have a declared CRS.")
                if ds.width*ds.height>MAX_PIXELS or ds.count>20:
                    raise HTTPException(413,"Raster exceeds prototype pixel or band limits.")
                from rasterio.warp import transform_bounds
                west,south,east,north=transform_bounds(ds.crs,"EPSG:4326",*ds.bounds,
                                                       densify_pts=21)
                bounds=[west,south,east,north]
                width,height,count=ds.width,ds.height,ds.count
                srid=ds.crs.to_epsg()
    except (rasterio.errors.RasterioError,ValueError) as exc:
        raise HTTPException(422,"Cannot read raster: "+str(exc)) from exc
    try:
        path.write_bytes(content)
        with geo_connection() as db:
            db.execute("""INSERT INTO raster_scenes(
                id,title,capture_date,platform,source_url,licence,local_filename,
                srid,bounds_wgs84,band_count,width,height)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (sid,title,day,platform,source_url,licence,path.name,srid,Jsonb(bounds),
                 count,width,height))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"id":str(sid),"title":title,"bands":count,"bounds":bounds}


@router.get("/scenes")
def scenes():
    with geo_connection() as db:
        rows=db.execute(
            """SELECT id,title,capture_date,platform,source_url,licence,
                      bounds_wgs84,band_count,width,height FROM raster_scenes
               ORDER BY capture_date DESC LIMIT 500""").fetchall()
    return [{"id":str(r[0]),"title":r[1],"capture_date":r[2].isoformat(),
             "platform":r[3],"source_url":r[4],"licence":r[5],"bounds":r[6],
             "bands":r[7],"width":r[8],"height":r[9]} for r in rows]


def find_scene(scene_id):
    with geo_connection() as db:
        row=db.execute("SELECT local_filename FROM raster_scenes WHERE id=%s",
                       (scene_id,)).fetchone()
    if not row:
        raise HTTPException(404,"Raster scene not found.")
    path=STORE/row[0]
    if not path.exists():
        raise HTTPException(404,"Local raster file missing.")
    return path


def stretched_byte(band,valid):
    values=band[valid & np.isfinite(band)]
    if not values.size:
        return np.zeros(band.shape,dtype=np.uint8)
    lo,hi=np.percentile(values,[2,98])
    if hi<=lo:
        hi=lo+1
    result=np.clip((band-lo)/(hi-lo)*255,0,255)
    result[~np.isfinite(result)]=0
    return result.astype(np.uint8)


@router.get("/scenes/{scene_id}/preview")
def preview(scene_id:uuid.UUID):
    path=find_scene(scene_id)
    with rasterio.open(path) as src, WarpedVRT(src,crs='EPSG:4326') as ds:
        factor=max(1,int(np.ceil(max(ds.width,ds.height)/1024)))
        shape=(max(1,ds.height//factor),max(1,ds.width//factor))
        indexes=(1,2,3) if ds.count>=3 else (1,)
        raw=ds.read(indexes,out_shape=(len(indexes),*shape),
                    resampling=Resampling.bilinear).astype(np.float32)
        mask=ds.read_masks(1,out_shape=shape)>0
        if len(indexes)==1:
            image=Image.fromarray(stretched_byte(raw[0],mask),"L")
        else:
            # RGB band assignment is user-dependent. This is display only.
            rgb=np.moveaxis(np.array([stretched_byte(b,mask) for b in raw]),0,-1)
            image=Image.fromarray(rgb,"RGB")
        buf=io.BytesIO()
        image.save(buf,format="PNG")
    return Response(content=buf.getvalue(),media_type="image/png",
                    headers={"Cache-Control":"private,max-age=3600"})


from pydantic import BaseModel,Field


class VegetationComparison(BaseModel):
    before_id:uuid.UUID
    after_id:uuid.UUID
    red_band:int=Field(default=1,ge=1,le=20)
    nir_band:int=Field(default=2,ge=1,le=20)
    ndvi_drop_threshold:float=Field(default=0.2,gt=0,le=1)


def calculate_ndvi(red,nir):
    denominator=nir+red
    return np.divide(nir-red,denominator,
                     out=np.full(red.shape,np.nan,dtype=np.float32),
                     where=np.abs(denominator)>1e-6)


@router.post("/compare-vegetation")
def compare_vegetation(body:VegetationComparison):
    """Exploratory same-area NDVI delta, not validated semantic change detection."""
    before,after=find_scene(body.before_id),find_scene(body.after_id)
    with rasterio.open(before) as a, rasterio.open(after) as b:
        if body.red_band>min(a.count,b.count) or body.nir_band>min(a.count,b.count):
            raise HTTPException(422,"Requested red/NIR band is absent.")
        if a.width*a.height>MAX_PIXELS:
            raise HTTPException(413,"Before image is too large.")
        ba=a.bounds;bb=b.bounds
        from rasterio.warp import transform_bounds
        b_in_a=transform_bounds(b.crs,a.crs,*bb)
        if ba.right<=b_in_a[0] or ba.left>=b_in_a[2] or ba.top<=b_in_a[1] or ba.bottom>=b_in_a[3]:
            raise HTTPException(422,"Rasters do not overlap geographically.")
        after_layers=[]
        for band in (body.red_band,body.nir_band):
            dst=np.full((a.height,a.width),np.nan,dtype=np.float32)
            reproject(source=rasterio.band(b,band),destination=dst,
                      src_nodata=b.nodata,dst_transform=a.transform,dst_crs=a.crs,
                      dst_nodata=np.nan,resampling=Resampling.bilinear)
            after_layers.append(dst)
        red0=a.read(body.red_band).astype(np.float32)
        nir0=a.read(body.nir_band).astype(np.float32)
        red1,nir1=after_layers
        valid=(a.read_masks(body.red_band)>0)&(a.read_masks(body.nir_band)>0)
        n0=calculate_ndvi(red0,nir0)
        n1=calculate_ndvi(red1,nir1)
        valid &= np.isfinite(n0)&np.isfinite(n1)
        if not np.any(valid):
            raise HTTPException(422,"No mutually valid overlapping pixels.")
        delta=(n1-n0)[valid]
        drop=delta < -body.ndvi_drop_threshold
        return {"before_id":str(body.before_id),"after_id":str(body.after_id),
                "valid_aligned_pixels":int(valid.sum()),
                "mean_ndvi_before":round(float(n0[valid].mean()),4),
                "mean_ndvi_after":round(float(n1[valid].mean()),4),
                "mean_ndvi_delta":round(float(delta.mean()),4),
                "fraction_with_ndvi_drop":round(float(drop.mean()),4),
                "method":"Reproject after raster onto before raster grid; masked band arithmetic.",
                "limitations":"Exploratory only. Red/NIR bands must be selected correctly for both sensors. "
                "Clouds, snow, atmospheric correction, seasonality, and registration "
                "error are not automatically suppressed. These outputs cannot establish "
                "deforestation, legal land-use change or causal policy impact."}


@router.delete("/scenes/{scene_id}")
def delete_scene(scene_id:uuid.UUID):
    with geo_connection() as db:
        row=db.execute("DELETE FROM raster_scenes WHERE id=%s RETURNING local_filename",
                       (scene_id,)).fetchone()
    if not row:
        raise HTTPException(404,"Scene not found.")
    (STORE/row[0]).unlink(missing_ok=True)
    return {"deleted":str(scene_id)}
