"""Validated execution context supplied to one selected module."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from planminpy.core.contracts import ContractValidationError, validate_identifier
from planminpy.core.paths import ProjectPaths, ResolvedDataset


@dataclass(frozen=True)
class ModuleContext:
    project_root: Path
    data_root: Path
    output_root: Path
    project_id: str
    dataset_id: str
    release_id: str
    dataset_path: Path
    manifest_path: Path
    manifest: Mapping[str, Any]
    topography_path: Path | None = None
    settings: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        project_root = Path(self.project_root).resolve()
        data_root = Path(self.data_root).resolve()
        output_root = Path(self.output_root).resolve(strict=False)
        dataset_path = Path(self.dataset_path).resolve()
        manifest_path = Path(self.manifest_path).resolve()
        topography_path = (
            None
            if self.topography_path is None
            else Path(self.topography_path).resolve()
        )

        if data_root != (project_root / "Data").resolve():
            raise ContractValidationError("context data_root is not project Data/")
        if output_root != (project_root / "outputs").resolve(strict=False):
            raise ContractValidationError("context output_root is not project outputs/")
        if dataset_path == output_root or dataset_path.is_relative_to(output_root):
            raise ContractValidationError("dataset_path cannot be beneath outputs/")
        if topography_path is not None and (
            topography_path == output_root or topography_path.is_relative_to(output_root)
        ):
            raise ContractValidationError("topography_path cannot be beneath outputs/")
        if manifest_path.parent != dataset_path or manifest_path.name != "release_manifest.json":
            raise ContractValidationError("manifest_path does not identify the resolved release")

        manifest = dict(self.manifest)
        for field_name in ("project_id", "dataset_id", "release_id"):
            expected = getattr(self, field_name)
            validate_identifier(field_name, expected)
            if manifest.get(field_name) != expected:
                raise ContractValidationError(
                    f"context {field_name} does not match release manifest"
                )

        settings = dict(self.settings)
        if not all(isinstance(key, str) for key in settings):
            raise ContractValidationError("context setting names must be strings")
        try:
            json.dumps(settings, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "context settings must contain JSON-compatible finite values"
            ) from exc

        object.__setattr__(self, "project_root", project_root)
        object.__setattr__(self, "data_root", data_root)
        object.__setattr__(self, "output_root", output_root)
        object.__setattr__(self, "dataset_path", dataset_path)
        object.__setattr__(self, "manifest_path", manifest_path)
        object.__setattr__(self, "manifest", MappingProxyType(manifest))
        object.__setattr__(self, "topography_path", topography_path)
        object.__setattr__(self, "settings", MappingProxyType(settings))


def create_module_context(
    paths: ProjectPaths,
    resolved_dataset: ResolvedDataset,
    *,
    topography_path: Path | str | None = None,
    settings: Mapping[str, Any] | None = None,
) -> ModuleContext:
    return ModuleContext(
        project_root=paths.project_root,
        data_root=paths.data_root,
        output_root=paths.output_root,
        project_id=resolved_dataset.project_id,
        dataset_id=resolved_dataset.dataset_id,
        release_id=resolved_dataset.release_id,
        dataset_path=resolved_dataset.dataset_path,
        manifest_path=resolved_dataset.manifest_path,
        manifest=resolved_dataset.manifest,
        topography_path=topography_path,
        settings={} if settings is None else settings,
    )
