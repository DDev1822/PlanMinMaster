from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from m01_test_support import CONFIG
from planminpy.core.contracts import ModuleResult, ModuleStatus
from planminpy.core.paths import ProjectPaths
from planminpy.interactive.contracts import ActiveProject, TerminalIO
from planminpy.interactive.project import (
    inspect_exploration_directory,
    inspect_topography,
)
from planminpy.modules.m01.loaders import SCHEMAS


def make_interactive_project(root: Path) -> tuple[ProjectPaths, ActiveProject]:
    data = root / "Data" / "arbitrary_release_folder"
    data.mkdir(parents=True)
    manifest = {
        "project_id": "quebrada_verde",
        "project_name": "Quebrada Verde",
        "dataset_id": "DS00",
        "release_id": "EXP03",
        "campaigns": ["C01"],
        "file_sha256": {},
    }
    (data / "release_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    rows = {
        "collar.csv": [
            {
                "hole_id": "H1",
                "dataset_id": "DS00",
                "project_id": "quebrada_verde",
                "campaign_id": "CAMPAIGN_01",
                "x": "0",
                "y": "0",
                "z": "100",
                "azimuth_deg": "0",
                "dip_deg": "-90",
                "final_depth_m": "20",
            }
        ],
        "survey.csv": [
            {
                "hole_id": "H1",
                "dataset_id": "DS00",
                "project_id": "quebrada_verde",
                "campaign_id": "CAMPAIGN_01",
                "depth_m": "0",
                "azimuth_deg": "0",
                "dip_deg": "-90",
            }
        ],
        "assay.csv": [
            {
                "sample_id": "S1",
                "hole_id": "H1",
                "dataset_id": "DS00",
                "project_id": "quebrada_verde",
                "campaign_id": "CAMPAIGN_01",
                "from_m": "0",
                "to_m": "10",
                "length_m": "10",
                "cu_pct": "0.1",
                "mo_pct": "0",
                "au_gt": "0",
            },
            {
                "sample_id": "S2",
                "hole_id": "H1",
                "dataset_id": "DS00",
                "project_id": "quebrada_verde",
                "campaign_id": "CAMPAIGN_01",
                "from_m": "10",
                "to_m": "20",
                "length_m": "10",
                "cu_pct": "0.3",
                "mo_pct": "0",
                "au_gt": "0",
            },
        ],
        "lithology.csv": [],
        "alteration.csv": [],
        "density.csv": [
            {
                "density_sample_id": "D1",
                "hole_id": "H1",
                "dataset_id": "DS00",
                "project_id": "quebrada_verde",
                "campaign_id": "CAMPAIGN_01",
                "from_m": "0",
                "to_m": "10",
                "length_m": "10",
                "density_t_m3": "2.5",
            }
        ],
    }
    for name, columns in SCHEMAS.items():
        with (data / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows[name])

    topography = root / "Data" / "surface_points.csv"
    topography.write_text(
        "PID,X,Y,Z\n1,0,0,100\n2,1,0,100\n3,0,1,100\n4,1,1,100\n",
        encoding="utf-8",
    )
    (root / "Data").mkdir(exist_ok=True)
    (root / "configs").mkdir(exist_ok=True)
    (root / "configs" / "m01.json").write_text(
        json.dumps(CONFIG), encoding="utf-8"
    )
    paths = ProjectPaths.from_project_root(root)
    exploration = inspect_exploration_directory(data)
    topo = inspect_topography(topography)
    active = ActiveProject(
        exploration_data_path=exploration.path,
        topography_path=topo.path,
        project_id="quebrada_verde",
        project_name="Quebrada Verde",
        dataset_id="DS00",
        release_id="EXP03",
        manifest_path=exploration.manifest_path,
        manifest=exploration.manifest,
        source_counts={**exploration.counts, "topography.csv": topo.point_count},
        analytical_variables=exploration.analytical_variables,
    )
    return paths, active


def terminal_with_inputs(values: Iterable[str]) -> tuple[TerminalIO, list[str]]:
    iterator = iter(values)
    output: list[str] = []
    return TerminalIO(input_fn=lambda _prompt: next(iterator), output_fn=output.append), output


def result_for(
    *,
    module_id: str = "m01",
    version: str = "1.1.0",
    status: ModuleStatus = ModuleStatus.COMPLETED,
    warnings: tuple[str, ...] = (),
    metrics: dict[str, object] | None = None,
) -> ModuleResult:
    now = datetime.now(timezone.utc)
    return ModuleResult(
        module_id=module_id,
        module_version=version,
        status=status,
        project_id="quebrada_verde",
        dataset_id="DS00",
        release_id="EXP03",
        started_at=now,
        completed_at=now,
        summary="test result",
        warnings=warnings,
        metrics={} if metrics is None else metrics,
    )
