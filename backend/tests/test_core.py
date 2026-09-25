"""Lightweight pure-function smoke tests for development logic.

Integration tests for PostGIS, account permissions, raster I/O and RAG
must run with the local services during final verification.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app.platform import password_hash, password_matches, scenario_calculation
from app.gis import validate_geojson
from app.raster import calculate_ndvi
import numpy as np


def test_password_roundtrip():
    hashed=password_hash("a long local test password")
    assert password_matches("a long local test password",hashed)
    assert not password_matches("incorrect password",hashed)


def test_simulation_arithmetic():
    result=scenario_calculation(SimpleNamespace(
        total_area_ha=1000,baseline_conversion_ha=100,
        proposed_restriction_fraction=0.5,assumed_compliance_fraction=0.6))
    assert result["hypothetical_avoided_conversion_ha"]==30
    assert result["hypothetical_conversion_ha"]==70
    assert "NOT a forecast" in result["warning"]


def test_geojson_validation():
    sample={"type":"FeatureCollection","features":[
        {"type":"Feature","geometry":{"type":"Point","coordinates":[77.45,28.67]},
         "properties":{"demo_only":True}}]}
    assert len(validate_geojson(sample))==1


def test_ndvi_math():
    red=np.array([[0.2]],dtype=np.float32)
    nir=np.array([[0.6]],dtype=np.float32)
    assert abs(float(calculate_ndvi(red,nir)[0,0])-0.5)<1e-5


# Stage 5: provenance-aware indicator ingest and descriptive series
from app.advanced import parse_indicator_csv, descriptive_trend
import pytest


def test_indicator_csv_roundtrip():
    csv_bytes=(
        b"state,district,year,indicator,value,unit,source_url,dataset_name\n"
        b"Uttar Pradesh,Ghaziabad,2020,Example area,123.5,ha,https://example.org/data,DEMO\n"
    )
    rows=parse_indicator_csv(csv_bytes)
    assert len(rows)==1
    assert rows[0][2]==2020 and rows[0][4]==123.5


def test_indicator_csv_rejects_nan_and_bad_source():
    prefix=b"state,district,year,indicator,value,unit,source_url,dataset_name\n"
    with pytest.raises(ValueError):
        parse_indicator_csv(prefix+b"UP,Ghaziabad,2020,area,nan,ha,https://example.org,Demo\n")
    with pytest.raises(ValueError):
        parse_indicator_csv(prefix+b"UP,Ghaziabad,2020,area,5,ha,file:///secret,Demo\n")


def test_trend_requires_comparable_units_and_unique_years():
    points=[
        {"year":2020,"value":100.0,"unit":"ha","source_url":"https://example.org","dataset_name":"Demo"},
        {"year":2021,"value":110.0,"unit":"ha","source_url":"https://example.org","dataset_name":"Demo"}
    ]
    trend=descriptive_trend(points)
    assert trend["changes"][0]["absolute_change"]==10
    assert trend["changes"][0]["percentage_change"]==10
    duplicated=descriptive_trend(points+[points[0]])
    assert duplicated["changes"]==[] and duplicated["ambiguous_years"]==[2020]
    mixed=descriptive_trend([points[0],dict(points[1],unit="km2")])
    assert mixed["changes"]==[]
