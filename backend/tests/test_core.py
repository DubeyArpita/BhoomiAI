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
