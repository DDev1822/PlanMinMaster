"""Common command-line interface for PlanMinPy module execution."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from planminpy.core.context import create_module_context
from planminpy.core.contracts import ModuleStatus, PlanMinPyError
from planminpy.core.paths import ProjectPaths, resolve_dataset
from planminpy.core.registry import create_default_registry
from planminpy.core.runner import ModuleRunner
from planminpy.interactive.dashboard import InteractiveDashboard
from planminpy.interactive.project import discover_topographies
from planminpy.reporting.reporter import Reporter


def _print_m01_summary(result: object, paths: ProjectPaths) -> None:
    metrics = result.metrics
    visualization = paths.output_root / str(metrics["visualization_relative_path"])
    print("M01 — VALIDATE, DESURVEY & DRILLHOLE ANALYSIS")
    print()
    print(f"Project: {result.project_id}")
    print(f"Dataset: {result.dataset_id}")
    print(f"Release: {result.release_id}")
    print()
    print(f"Drillholes:              {metrics['hole_count']}")
    print(f"Drilled metres:          {float(metrics['total_drilled_m']):,.2f}")
    print(f"Assays:                  {metrics['assay_count']}")
    print()
    print("Validation:")
    print(f"Errors:                  {metrics['validation_error_count']}")
    print(f"Warnings:                {metrics['validation_warning_count']}")
    print()
    print("Desurvey:                COMPLETED")
    print(f"Assays positioned in 3D: {metrics['assays_positioned_count']}")
    print()
    print("OBSERVED Cu DISTRIBUTION")
    print(f"Minimum:                 {float(metrics['observed_grade_minimum']):.5f} %")
    print(f"Maximum:                 {float(metrics['observed_grade_maximum']):.5f} %")
    print(f"Mean:                    {float(metrics['observed_grade_mean']):.5f} %")
    print(f"Median:                  {float(metrics['observed_grade_median']):.5f} %")
    print()
    if not bool(metrics.get("reference_grade_analysis_enabled", False)):
        print("Reference-grade analysis: NOT REQUESTED")
    else:
        print("REFERENCE-GRADE INTERCEPT ANALYSIS")
        print(f"Reference grade:         {float(metrics['reference_grade']):.2f} % Cu")
        print(f"Intercepts:              {metrics['reference_grade_intercept_count']}")
        print(
            f"Intercept metres:        {float(metrics['reference_grade_intercept_metres']):,.2f}"
        )
        print(f"Drillholes represented:  {metrics['reference_grade_drillhole_count']}")
        print("Interpretation:          ALONG-HOLE; NOT TRUE GEOLOGICAL THICKNESS")
        print("Reference grade is NOT an economic cut-off grade.")
    print()
    print("M01 does NOT calculate Mineral Resources.")
    print()
    print("3D View:")
    print(visualization)
    print()
    print(f"Status: {metrics['validation_status']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planminpy",
        description="PlanMinPy educational mine-planning application",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List registered modules")

    run_parser = subparsers.add_parser("run", help="Run one selected module")
    run_parser.add_argument("module_id", metavar="MODULE_ID")
    run_parser.add_argument("--dataset", required=True, dest="dataset_id")
    run_parser.add_argument("--release", required=True, dest="release_id")
    run_parser.add_argument("--project", dest="project_id")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    project_root: Path | str | None = None,
) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    root = Path.cwd() if project_root is None else Path(project_root)
    if not effective_argv:
        try:
            paths = ProjectPaths.from_project_root(root)
            registry = create_default_registry()
            return InteractiveDashboard(paths, registry).run()
        except PlanMinPyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    parser = build_parser()
    args = parser.parse_args(effective_argv)
    registry = create_default_registry()

    try:
        if args.command == "list":
            for descriptor in registry.list_modules():
                print(
                    f"{descriptor.module_id}\t{descriptor.title}\t{descriptor.version}"
                )
            return 0

        registry.get_module_descriptor(args.module_id)
        paths = ProjectPaths.from_project_root(root)
        resolved = resolve_dataset(
            paths,
            dataset_id=args.dataset_id,
            release_id=args.release_id,
            project_id=args.project_id,
        )
        topography_path = None
        if args.module_id == "m01":
            topographies = discover_topographies(paths.data_root)
            if not topographies:
                raise PlanMinPyError(
                    "no schema-valid topography CSV was detected directly inside Data/"
                )
            if len(topographies) > 1:
                raise PlanMinPyError(
                    "multiple topography CSVs were detected; use the interactive dashboard to select one"
                )
            topography_path = topographies[0].path
        context = create_module_context(
            paths, resolved, topography_path=topography_path
        )
        result = ModuleRunner(registry).run(args.module_id, context)
        report_output = Reporter(paths).update(result)

        if result.module_id == "m01" and result.module_version == "1.1.0":
            _print_m01_summary(result, paths)
        else:
            print(
                f"module={result.module_id} status={result.status.value} "
                f"project={result.project_id} dataset={result.dataset_id} "
                f"release={result.release_id}"
            )
            print(f"summary={result.summary}")
        print(f"report_state={report_output.state_path}")
        print(f"report_markdown={report_output.markdown_path}")
        return 1 if result.status is ModuleStatus.FAILED else 0
    except PlanMinPyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
