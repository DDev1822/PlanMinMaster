"""Small contracts shared by the generic dashboard and module-owned wizards."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from planminpy.core.context import ModuleContext, create_module_context
from planminpy.core.contracts import ModuleResult
from planminpy.core.paths import ProjectPaths, ResolvedDataset


@dataclass(frozen=True)
class ActiveProject:
    exploration_data_path: Path
    topography_path: Path
    project_id: str
    project_name: str
    dataset_id: str
    release_id: str
    manifest_path: Path
    manifest: Mapping[str, Any]
    source_counts: Mapping[str, int]
    analytical_variables: Mapping[str, str]

    def create_context(
        self,
        paths: ProjectPaths,
        settings: Mapping[str, Any],
    ) -> ModuleContext:
        resolved = ResolvedDataset(
            dataset_path=self.exploration_data_path,
            manifest_path=self.manifest_path,
            project_id=self.project_id,
            dataset_id=self.dataset_id,
            release_id=self.release_id,
            manifest=self.manifest,
        )
        return create_module_context(
            paths,
            resolved,
            topography_path=self.topography_path,
            settings=settings,
        )


@dataclass
class TerminalIO:
    input_fn: Callable[[str], str] = field(default_factory=lambda: input)
    output_fn: Callable[[str], None] = field(default_factory=lambda: print)

    def write(self, value: object = "") -> None:
        self.output_fn(str(value))

    def prompt(self, label: str) -> str:
        self.write(label)
        return self.input_fn("> ").strip()


class WizardAction(str, Enum):
    BACK = "BACK"
    CONFIGURE_DATA = "CONFIGURE_DATA"
    RUN = "RUN"


@dataclass(frozen=True)
class WizardOutcome:
    action: WizardAction
    settings: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WizardRequest:
    paths: ProjectPaths
    project: ActiveProject | None
    settings: Mapping[str, Any]
    last_result: ModuleResult | None
    io: TerminalIO
    open_path: Callable[[Path], bool]
    report_state_path: Path | None = None
    report_markdown_path: Path | None = None
    open_web_path: Callable[[Path], bool] | None = None


class ModuleWizard(Protocol):
    def interact(self, request: WizardRequest) -> WizardOutcome: ...

    def show_result(self, result: ModuleResult, request: WizardRequest) -> None: ...
