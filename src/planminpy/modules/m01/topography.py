"""Deterministic Qhull-backed topographic surface evaluation."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy
from scipy.spatial import Delaunay, cKDTree

from planminpy.core.contracts import PlanMinPyError


class TopographyError(PlanMinPyError):
    """Raised when the shared topographic source cannot define a surface."""


@dataclass(frozen=True)
class TopographyEvaluation:
    topography_z: float | None
    nearest_support_distance_m: float
    support_status: str


def classify_topography_consistency(
    delta_z_m: float | None,
    support_status: str,
    *,
    warning_tolerance_m: float,
    review_tolerance_m: float,
) -> str:
    """Apply explicit educational collar/topography consistency thresholds."""

    if delta_z_m is None or support_status == "OUTSIDE_CONVEX_HULL":
        return "ERROR"
    absolute_delta = abs(delta_z_m)
    if absolute_delta <= warning_tolerance_m:
        return "OK"
    if absolute_delta <= review_tolerance_m:
        return "WARNING"
    return "REQUIRES_REVIEW"


class TopographySurface:
    method_identifier = "SCIPY_QHULL_DELAUNAY_LINEAR_BARYCENTRIC"

    def __init__(self, pid: np.ndarray, xy: np.ndarray, z: np.ndarray) -> None:
        if len(pid) < 3 or xy.shape != (len(pid), 2) or z.shape != (len(pid),):
            raise TopographyError("topography requires at least three XYZ points")
        if not np.isfinite(xy).all() or not np.isfinite(z).all():
            raise TopographyError("topography contains missing or non-finite XYZ")
        order = np.lexsort((pid, xy[:, 1], xy[:, 0]))
        self.pid = pid[order]
        self.xy = xy[order]
        self.z = z[order]
        if len(np.unique(self.xy, axis=0)) != len(self.xy):
            raise TopographyError("topography contains duplicate XY coordinates")
        self._exact = {
            (float(point[0]), float(point[1])): float(value)
            for point, value in zip(self.xy, self.z, strict=True)
        }
        self._triangulation = Delaunay(self.xy)
        self._tree = cKDTree(self.xy)

    @classmethod
    def from_csv(cls, path: Path) -> TopographySurface:
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                header = tuple(next(csv.reader(handle)))
            if header != ("PID", "X", "Y", "Z"):
                raise TopographyError(f"unexpected topography schema: {header}")
            values = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float64)
        except (OSError, UnicodeError, ValueError) as exc:
            raise TopographyError(f"cannot load topography: {path}") from exc
        if values.ndim != 2 or values.shape[1] != 4:
            raise TopographyError("topography must contain PID,X,Y,Z rows")
        return cls(values[:, 0], values[:, 1:3], values[:, 3])

    @property
    def numpy_version(self) -> str:
        return np.__version__

    @property
    def scipy_version(self) -> str:
        return scipy.__version__

    @property
    def triangle_vertex_indices(self) -> np.ndarray:
        """Return a copy of the validated full-resolution TIN connectivity."""

        return self._triangulation.simplices.copy()

    def evaluate(self, x: float, y: float) -> TopographyEvaluation:
        query = np.array([x, y], dtype=np.float64)
        nearest_distance, _ = self._tree.query(query, k=1)
        exact = self._exact.get((float(x), float(y)))
        if exact is not None:
            return TopographyEvaluation(exact, float(nearest_distance), "EXACT_XY")
        simplex = int(self._triangulation.find_simplex(query))
        if simplex < 0:
            return TopographyEvaluation(None, float(nearest_distance), "OUTSIDE_CONVEX_HULL")
        transform = self._triangulation.transform[simplex]
        first = transform[:2].dot(query - transform[2])
        weights = np.append(first, 1.0 - first.sum())
        vertices = self._triangulation.simplices[simplex]
        value = float(weights.dot(self.z[vertices]))
        return TopographyEvaluation(value, float(nearest_distance), "TIN_INTERPOLATED")
