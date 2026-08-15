from __future__ import annotations

import json
from pathlib import Path

from planminpy.core.context import ModuleContext, create_module_context
from planminpy.core.paths import ProjectPaths, resolve_dataset
from planminpy.modules.m01.config import M01Config, load_config
from planminpy.modules.m01.loaders import SCHEMAS, TableData


CONFIG = {
    "schema_version": "m01.config.v1.1",
    "coordinate_system": {
        "semantic": "LOCAL_CARTESIAN",
        "unit": "metre",
        "crs_identifier": None,
        "x_axis": "EASTING",
        "y_axis": "NORTHING",
        "z_axis": "POSITIVE_UP",
        "azimuth_convention": "CLOCKWISE_FROM_NORTH",
        "dip_convention": "NEGATIVE_DOWN",
    },
    "campaign_aliases": {
        "C01": "CAMPAIGN_01",
        "C02": "CAMPAIGN_02",
        "C03": "CAMPAIGN_03",
    },
    "numeric": {
        "interval_length_abs_tolerance_m": 1e-6,
        "zero_dogleg_epsilon_rad": 1e-7,
    },
    "survey": {
        "station_spacing_warning_m": 50.0,
        "station_spacing_review_m": 100.0,
        "terminal_gap_warning_m": 25.0,
        "terminal_gap_review_m": 50.0,
        "dogleg_normalization_m": 30.0,
        "dogleg_warning_deg_per_normalization": 3.0,
        "dogleg_review_deg_per_normalization": 6.0,
    },
    "density": {"review_min_t_m3": 1.5, "review_max_t_m3": 4.5},
    "topography": {
        "surface_method": "SCIPY_QHULL_DELAUNAY_LINEAR_BARYCENTRIC",
        "warning_tolerance_m": 2.0,
        "review_tolerance_m": 5.0,
    },
    "analysis": {
        "primary_element": "cu_pct",
        "unit": "%",
    },
    "grade_distribution": {
        "boundaries": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "interval_semantic": "LOWER_INCLUSIVE_UPPER_EXCLUSIVE",
        "final_bin": "OPEN_ENDED",
    },
    "reference_grade_analysis": {
        "enabled_by_default": False,
        "default_reference_grade": 0.20,
        "unit": "%",
        "purpose": "drillhole_intercept_reference_only",
    },
    "visualization": {
        "maximum_topography_vertices": 25000,
        "topography_label": "visualization-decimated",
    },
}


def make_project(root: Path) -> tuple[ModuleContext, M01Config]:
    release = root / "Data" / "PL00"
    release.mkdir(parents=True)
    manifest = {
        "project_id": "project",
        "dataset_id": "DS00",
        "release_id": "EXP03",
        "campaigns": ["C01", "C02", "C03"],
        "n_alteration_intervals": 0,
        "file_sha256": {},
    }
    (release / "release_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    config_dir = root / "configs"
    config_dir.mkdir()
    (config_dir / "m01.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    paths = ProjectPaths.from_project_root(root)
    context = create_module_context(paths, resolve_dataset(paths, "DS00", "EXP03"))
    return context, load_config(root)


def collar(**updates: str) -> dict[str, str]:
    row = {
        "hole_id": "QV-C01-001",
        "dataset_id": "DS00",
        "project_id": "project",
        "campaign_id": "CAMPAIGN_01",
        "x": "0",
        "y": "0",
        "z": "100",
        "azimuth_deg": "0",
        "dip_deg": "-90",
        "final_depth_m": "100",
    }
    row.update(updates)
    return row


def survey(**updates: str) -> dict[str, str]:
    row = {
        "hole_id": "QV-C01-001",
        "dataset_id": "DS00",
        "project_id": "project",
        "campaign_id": "CAMPAIGN_01",
        "depth_m": "0",
        "azimuth_deg": "0",
        "dip_deg": "-90",
    }
    row.update(updates)
    return row


def interval(table_name: str, **updates: str) -> dict[str, str]:
    row = {column: "" for column in SCHEMAS[table_name]}
    row.update(
        {
            "hole_id": "QV-C01-001",
            "dataset_id": "DS00",
            "project_id": "project",
            "campaign_id": "CAMPAIGN_01",
            "from_m": "0",
            "to_m": "10",
            "length_m": "10",
        }
    )
    if table_name == "assay.csv":
        row.update({"sample_id": "S1", "cu_pct": "1", "mo_pct": "0", "au_gt": "0"})
    if table_name == "density.csv":
        row.update({"density_sample_id": "D1", "density_t_m3": "2.5"})
    if table_name == "lithology.csv":
        row["lith_code"] = "POR"
    if table_name == "alteration.csv":
        row.update({"alteration_code": "", "alteration_intensity": ""})
    row.update(updates)
    return row


def table(root: Path, name: str, rows: list[dict[str, str]]) -> TableData:
    return TableData(name, root / name, SCHEMAS[name], tuple(rows))
