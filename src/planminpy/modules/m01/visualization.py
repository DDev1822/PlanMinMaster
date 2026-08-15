"""Offline Plotly visualization for the M01 classroom result."""

from __future__ import annotations

import importlib.metadata
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from scipy.spatial import Delaunay

from planminpy.modules.m01.topography import TopographySurface


def _decimated_topography_mesh(
    surface: TopographySurface,
    maximum_vertices: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    count = min(maximum_vertices, len(surface.xy))
    indices = np.linspace(0, len(surface.xy) - 1, num=count, dtype=np.int64)
    indices = np.unique(indices)
    xy = surface.xy[indices]
    z = surface.z[indices]
    triangulation = Delaunay(xy)
    return xy, z, triangulation.simplices


def build_exploration_3d_html(
    surface: TopographySurface,
    trajectory_rows: Sequence[Mapping[str, Any]],
    assay_xyz_rows: Sequence[Mapping[str, Any]],
    *,
    reference_grade: float | None,
    maximum_topography_vertices: int,
    project_id: str,
    dataset_id: str,
    release_id: str,
) -> tuple[str, dict[str, Any]]:
    """Build the three required layers plus an optional reference-grade trace."""

    topo_xy, topo_z, topo_triangles = _decimated_topography_mesh(
        surface, maximum_topography_vertices
    )
    figure = go.Figure()
    figure.add_trace(
        go.Mesh3d(
            name="Topography (visualization-decimated)",
            x=topo_xy[:, 0],
            y=topo_xy[:, 1],
            z=topo_z,
            i=topo_triangles[:, 0],
            j=topo_triangles[:, 1],
            k=topo_triangles[:, 2],
            intensity=topo_z,
            colorscale="Earth",
            opacity=0.58,
            showscale=True,
            colorbar={"title": "Elevation (m)", "x": 0.98},
            hovertemplate="Topo X=%{x:.2f}<br>Y=%{y:.2f}<br>Z=%{z:.2f} m<extra></extra>",
        )
    )

    trajectory_groups: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in trajectory_rows:
        trajectory_groups[str(row["hole_id"])].append(row)
    trajectory_x: list[float | None] = []
    trajectory_y: list[float | None] = []
    trajectory_z: list[float | None] = []
    trajectory_custom: list[list[Any] | None] = []
    for hole_id in sorted(trajectory_groups):
        for row in sorted(trajectory_groups[hole_id], key=lambda item: float(item["md_m"])):
            trajectory_x.append(float(row["x"]))
            trajectory_y.append(float(row["y"]))
            trajectory_z.append(float(row["z"]))
            trajectory_custom.append(
                [hole_id, row["campaign_id"], float(row["md_m"])]
            )
        trajectory_x.append(None)
        trajectory_y.append(None)
        trajectory_z.append(None)
        trajectory_custom.append(None)
    figure.add_trace(
        go.Scatter3d(
            name="Drillhole trajectories",
            mode="lines",
            x=trajectory_x,
            y=trajectory_y,
            z=trajectory_z,
            customdata=trajectory_custom,
            line={"color": "#17202A", "width": 4},
            hovertemplate=(
                "Hole=%{customdata[0]}<br>Campaign=%{customdata[1]}"
                "<br>MD=%{customdata[2]:.2f} m<extra></extra>"
            ),
        )
    )

    assay_custom = [
        [row["hole_id"], float(row["from_m"]), float(row["to_m"]), float(row["cu_pct"])]
        for row in assay_xyz_rows
    ]
    figure.add_trace(
        go.Scatter3d(
            name="Assay Cu midpoint",
            mode="markers",
            x=[float(row["x_mid"]) for row in assay_xyz_rows],
            y=[float(row["y_mid"]) for row in assay_xyz_rows],
            z=[float(row["z_mid"]) for row in assay_xyz_rows],
            customdata=assay_custom,
            marker={
                "size": 3,
                "color": [float(row["cu_pct"]) for row in assay_xyz_rows],
                "colorscale": "Turbo",
                "showscale": True,
                "colorbar": {"title": "Cu (%)", "x": 1.08},
                "opacity": 0.85,
            },
            hovertemplate=(
                "Hole=%{customdata[0]}<br>FROM=%{customdata[1]:.2f} m"
                "<br>TO=%{customdata[2]:.2f} m<br>Cu=%{customdata[3]:.3f}%<extra></extra>"
            ),
        )
    )

    reference_assay_count = 0
    if reference_grade is not None:
        reference_x: list[float | None] = []
        reference_y: list[float | None] = []
        reference_z: list[float | None] = []
        reference_custom: list[list[Any] | None] = []
        for row in assay_xyz_rows:
            grade = float(row["cu_pct"])
            if grade < reference_grade:
                continue
            reference_assay_count += 1
            custom = [row["hole_id"], float(row["from_m"]), float(row["to_m"]), grade]
            reference_x.extend([float(row["x_from"]), float(row["x_to"]), None])
            reference_y.extend([float(row["y_from"]), float(row["y_to"]), None])
            reference_z.extend([float(row["z_from"]), float(row["z_to"]), None])
            reference_custom.extend([custom, custom, None])
        figure.add_trace(
            go.Scatter3d(
                name=f"Reference-grade intervals >= {reference_grade:.2f}% Cu",
                mode="lines",
                x=reference_x,
                y=reference_y,
                z=reference_z,
                customdata=reference_custom,
                line={"color": "#E74C3C", "width": 8},
                hovertemplate=(
                    "Hole=%{customdata[0]}<br>FROM=%{customdata[1]:.2f} m"
                    "<br>TO=%{customdata[2]:.2f} m<br>Cu=%{customdata[3]:.3f}%<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        title=(
            "PlanMinPy M01 — Validate, Desurvey & Drillhole Analysis"
            f"<br><sup>{project_id} / {dataset_id} / {release_id}; "
            "topography is visualization-decimated</sup>"
        ),
        template="plotly_white",
        legend={"orientation": "h", "y": 1.02, "x": 0.0},
        margin={"l": 0, "r": 0, "t": 90, "b": 0},
        scene={
            "xaxis_title": "Easting X (m)",
            "yaxis_title": "Northing Y (m)",
            "zaxis_title": "Elevation Z (m)",
            "aspectmode": "data",
        },
    )
    html = pio.to_html(
        figure,
        full_html=True,
        include_plotlyjs=True,
        div_id="planminpy-m01-exploration-3d",
        config={"responsive": True, "displaylogo": False},
        auto_play=False,
    )
    metadata = {
        "plotly_version": importlib.metadata.version("plotly"),
        "offline": True,
        "include_plotlyjs": True,
        "topography_source_point_count": int(len(surface.xy)),
        "topography_display_vertex_count": int(len(topo_xy)),
        "topography_display_classification": "VISUALIZATION_DECIMATED",
        "trajectory_station_count": len(trajectory_rows),
        "assay_midpoint_count": len(assay_xyz_rows),
        "reference_grade_analysis_enabled": reference_grade is not None,
        "reference_grade": reference_grade,
        "reference_grade_assay_count": reference_assay_count,
        "trace_names": [trace.name for trace in figure.data],
    }
    return html, metadata
