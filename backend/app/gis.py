"""Stage 2 geospatial APIs: local GeoJSON datasets backed by PostGIS.

Accepts GeoJSON with EPSG:4326 lon/lat coordinates only.
Prototype limits intentionally cap uploads and returned map features.
"""
import json
import logging
import os
import uuid
from contextlib import contextmanager

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from psycopg.types.json import Jsonb

router = APIRouter(prefix="/gis", tags=["GIS"])
logger = logging.getLogger(__name__)
GEO_DATABASE_URL = os.getenv(
    "GEO_DATABASE_URL",
    "postgresql://bhoomi_geo:bhoomi_geo_dev_only@localhost:5434/bhoomi_geo",
)
ALLOWED_GEOMETRIES = {
    "Point", "MultiPoint", "LineString", "MultiLineString",
    "Polygon", "MultiPolygon",
}
MAX_GEOJSON_BYTES = 10 * 1024 * 1024
MAX_FEATURES = 5000


@contextmanager
def geo_connection():
    try:
        with psycopg.connect(GEO_DATABASE_URL, connect_timeout=3) as db:
            yield db
    except psycopg.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail="GIS database is unavailable. Start Docker with docker compose up -d.",
        ) from exc


def init_geo_database():
    with geo_connection() as db:
        db.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        db.execute("""
            CREATE TABLE IF NOT EXISTS geo_layers (
                id UUID PRIMARY KEY,
                name TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                licence TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS geo_features (
                id BIGSERIAL PRIMARY KEY,
                layer_id UUID NOT NULL REFERENCES geo_layers(id) ON DELETE CASCADE,
                geometry geometry(Geometry, 4326) NOT NULL,
                properties JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_geo_features_geometry
            ON geo_features USING GIST (geometry)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_geo_features_layer
            ON geo_features (layer_id)
        """)


def validate_geojson(data):
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise HTTPException(422, "Upload a GeoJSON FeatureCollection.")
    # RFC 7946 coordinates are WGS84 longitude,latitude; explicit alternate
    # CRS definitions are not converted silently.
    if data.get("crs"):
        raise HTTPException(422, "Re-export the GeoJSON in EPSG:4326 without a crs member.")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise HTTPException(422, "FeatureCollection must contain at least one feature.")
    if len(features) > MAX_FEATURES:
        raise HTTPException(413, f"Maximum {MAX_FEATURES} features per upload.")
    prepared = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise HTTPException(422, f"Item {index} is not a GeoJSON Feature.")
        geom = feature.get("geometry")
        if not isinstance(geom, dict) or geom.get("type") not in ALLOWED_GEOMETRIES:
            raise HTTPException(422, f"Feature {index} has an unsupported geometry.")
        if not isinstance(feature.get("properties", {}), dict):
            raise HTTPException(422, f"Feature {index} properties must be an object.")
        prepared.append((json.dumps(geom), Jsonb(feature.get("properties", {}))))
    return prepared


@router.get("/health")
def gis_health():
    with geo_connection() as db:
        result = db.execute("SELECT PostGIS_Version()").fetchone()
    return {"status": "ok", "postgis": result[0]}


@router.post("/layers", status_code=201)
async def import_layer(
    file: UploadFile = File(...),
    name: str = Form(min_length=2, max_length=140),
    source_url: str = Form(default="", max_length=1000),
    licence: str = Form(default="", max_length=150),
    description: str = Form(default="", max_length=1000),
):
    if not (file.filename or "").lower().endswith((".geojson", ".json")):
        raise HTTPException(400, "Only .geojson and .json files are accepted.")
    if source_url and not source_url.startswith(("https://", "http://")):
        raise HTTPException(422, "Source URL must start with http:// or https://")
    content = await file.read(MAX_GEOJSON_BYTES + 1)
    if len(content) > MAX_GEOJSON_BYTES:
        raise HTTPException(413, "GeoJSON exceeds 10 MB.")
    try:
        data = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, "Invalid GeoJSON JSON.") from exc
    prepared = validate_geojson(data)
    layer_id = uuid.uuid4()
    with geo_connection() as db:
        db.execute(
            "INSERT INTO geo_layers (id,name,source_url,licence,description) "
            "VALUES (%s,%s,%s,%s,%s)",
            (layer_id, name.strip(), source_url.strip(), licence.strip(), description.strip()),
        )
        with db.cursor() as cur:
            for index, (geom_json, properties) in enumerate(prepared):
                try:
                    # ST_GeomFromGeoJSON and database constraints catch malformed
                    # coordinates and geometry; keep entire layer atomic.
                    cur.execute(
                        """INSERT INTO geo_features (layer_id,geometry,properties)
                           SELECT %s, geom, %s
                           FROM (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) geom) x
                           WHERE ST_IsValid(geom)
                             AND ST_XMin(geom) >= -180 AND ST_XMax(geom) <= 180
                             AND ST_YMin(geom) >= -90 AND ST_YMax(geom) <= 90
                           RETURNING id""",
                        (layer_id, properties, geom_json),
                    )
                    if not cur.fetchone():
                        raise ValueError(f"Feature {index} has invalid/out-of-range coordinates.")
                except (psycopg.Error, ValueError) as exc:
                    db.rollback()
                    raise HTTPException(422, f"Invalid geometry at feature {index}: {exc}") from exc
    return {"id": str(layer_id), "name": name.strip(), "features": len(prepared)}


@router.get("/layers")
def list_layers():
    with geo_connection() as db:
        rows = db.execute("""
            SELECT l.id,l.name,l.source_url,l.licence,l.description,l.created_at,
                   COUNT(f.id)
            FROM geo_layers l LEFT JOIN geo_features f ON f.layer_id=l.id
            GROUP BY l.id ORDER BY l.created_at DESC
        """).fetchall()
    return [
        {"id": str(r[0]), "name": r[1], "source_url": r[2], "licence": r[3],
         "description": r[4], "created_at": r[5].isoformat(), "feature_count": r[6]}
        for r in rows
    ]


@router.get("/layers/{layer_id}/features")
def get_layer_features(
    layer_id: uuid.UUID,
    limit: int = Query(default=1000, ge=1, le=5000),
):
    with geo_connection() as db:
        layer = db.execute(
            "SELECT name FROM geo_layers WHERE id=%s", (layer_id,),
        ).fetchone()
        if not layer:
            raise HTTPException(404, "Layer not found.")
        rows = db.execute(
            "SELECT id,ST_AsGeoJSON(geometry),properties FROM geo_features "
            "WHERE layer_id=%s ORDER BY id LIMIT %s", (layer_id, limit),
        ).fetchall()
    return {
        "type": "FeatureCollection",
        "name": layer[0],
        "features": [
            {"type": "Feature", "id": row[0], "geometry": json.loads(row[1]),
             "properties": row[2]}
            for row in rows
        ],
        "truncated": len(rows) == limit,
    }


@router.delete("/layers/{layer_id}")
def delete_layer(layer_id: uuid.UUID):
    with geo_connection() as db:
        row = db.execute(
            "DELETE FROM geo_layers WHERE id=%s RETURNING name", (layer_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Layer not found.")
    return {"deleted": str(layer_id), "name": row[0]}
