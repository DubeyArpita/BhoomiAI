"""Offline regression tests for official boundary import and WorldCover class areas."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi import HTTPException
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.gis import validate_geojson
from app.raster import summarize_landcover


def boundary():
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {
            "name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [{
            "type": "Feature",
            "properties": {"DISTRICT": "GHAZIABAD"},
            "geometry": {"type": "MultiPolygon", "coordinates": [[[
                [77.01, 28.01, 0], [77.09, 28.01, 0],
                [77.09, 28.09, 0], [77.01, 28.09, 0],
                [77.01, 28.01, 0],
            ]]]},
        }],
    }


def test_qgis_crs84_and_z_are_importable_without_changing_original():
    supplied = boundary()
    converted = validate_geojson(supplied)
    assert len(converted) == 1
    geometry = json.loads(converted[0][0])
    assert geometry["type"] == "MultiPolygon"
    assert geometry["coordinates"][0][0][0] == [77.01, 28.01]
    assert supplied["features"][0]["geometry"]["coordinates"][0][0][0] == [77.01, 28.01, 0]


def test_other_crs_still_requires_explicit_qgis_reprojection():
    supplied = boundary()
    supplied["crs"]["properties"]["name"] = "EPSG:3857"
    with pytest.raises(HTTPException) as error:
        validate_geojson(supplied)
    assert error.value.status_code == 422


def test_worldcover_category_area_with_district_mask(tmp_path):
    path = tmp_path / "synthetic_classes.tif"
    classes = np.full((10, 10), 40, dtype=np.uint8)
    classes[:, 5:] = 50
    with rasterio.open(
        path, "w", driver="GTiff", height=10, width=10, count=1,
        dtype="uint8", crs="EPSG:4326",
        transform=from_origin(77.0, 28.1, 0.01, 0.01), nodata=0,
    ) as dataset:
        dataset.write(classes, 1)
    polygon = boundary()["features"][0]["geometry"]
    result = summarize_landcover(path, {
        **polygon,
        "coordinates": [[[[x, y] for x, y, _ in ring]
                          for ring in polygon["coordinates"][0]]],
    })
    assert result["analysed_pixels"] > 0
    category_codes = {row["code"] for row in result["categories"]}
    assert category_codes == {40, 50}
    assert all(row["area_ha"] > 0 for row in result["categories"])
    assert result["analysed_area_ha"] > 0
