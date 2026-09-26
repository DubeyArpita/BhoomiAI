"""Check exact schemas and Ghaziabad rows against the committed source files.

These assertions deliberately fail if the source portal changes headers,
rather than silently substituting a guessed metric or a statewide total.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.dilrmp import data_for_district, clean_district, REPORTS, locate, read_report


def test_district_name_normalization():
    assert clean_district("  Ghaziabad  ") == "GHAZIABAD"
    assert clean_district("  Sant   Kabir   Nagar ") == "SANT KABIR NAGAR"


def test_all_four_committed_reports_have_actual_ghaziabad_row():
    payload = data_for_district("Ghaziabad")
    assert payload["missing_reports"] == []
    assert {r["key"] for r in payload["reports"]} == set(REPORTS)
    for item in payload["reports"]:
        path = locate(item["key"])
        assert path is not None and path.exists()
        assert item["source_url"].startswith("https://")
        assert item["row"] >= 9
        assert all(field["cell"].endswith(str(item["row"])) for field in item["fields"])


def test_current_committed_source_numbers_are_not_state_totals():
    reports = {r["key"]: r for r in data_for_district("Ghaziabad")["reports"]}
    get = lambda group, key: next(
        field["value"] for field in reports[group]["fields"] if field["key"] == key
    )
    assert get("clr", "total_villages") == 264
    assert get("clr", "ror_total") == 266
    assert get("maps", "total_cadastral_maps") == 198
    assert get("maps", "georeferenced_land_parcels") == 118867
    assert get("mrr", "mrr_completed") == 0
    assert get("survey", "rural_revenue_area") == 882.27738


def test_state_report_includes_many_districts_not_just_ghaziabad():
    path = locate("mrr")
    _, district_rows = read_report("mrr", str(path), path.stat().st_mtime_ns)
    assert len(district_rows) >= 70
    assert "GHAZIABAD" in district_rows
    assert "AGRA" in district_rows


def test_categorical_worldcover_preview_preserves_classes():
    import numpy as np
    from app.raster import colorize_worldcover, WORLDCOVER_PALETTE
    classes=np.array([[10,40,50,0],[80,95,100,20]],dtype=np.uint8)
    valid=np.array([[True,True,True,False],[True,True,True,True]])
    rgba=colorize_worldcover(classes,valid)
    assert rgba.shape==(2,4,4)
    assert tuple(rgba[0,0,:3])==WORLDCOVER_PALETTE[10]
    assert tuple(rgba[0,2,:3])==WORLDCOVER_PALETTE[50]
    assert rgba[0,3,3]==0
    assert (rgba[:,:,3]==255).sum()==7
