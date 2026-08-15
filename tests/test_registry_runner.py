from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

from planminpy.core.context import ModuleContext, create_module_context
from planminpy.core.contracts import ModuleResult, ModuleStatus
from planminpy.core.paths import ProjectPaths, resolve_dataset
from planminpy.core.registry import (
    ModuleDescriptor,
    ModuleRegistry,
    UnknownModuleError,
    create_default_registry,
)
from planminpy.core.runner import ModuleIdentityError, ModuleRunner


def make_result(
    context: ModuleContext,
    *,
    module_id: str = "m01",
    version: str = "0.1.0",
    dataset_id: str | None = None,
) -> ModuleResult:
    now = datetime.now(timezone.utc)
    return ModuleResult(
        module_id=module_id,
        module_version=version,
        status=ModuleStatus.COMPLETED,
        project_id=context.project_id,
        dataset_id=context.dataset_id if dataset_id is None else dataset_id,
        release_id=context.release_id,
        started_at=now,
        completed_at=now,
        summary=f"result from {module_id}",
    )


class RegistryRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        manifest_dir = root / "Data" / "PL00"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "release_manifest.json").write_text(
            json.dumps(
                {
                    "project_id": "quebrada_verde",
                    "dataset_id": "DS00",
                    "release_id": "EXP03",
                }
            ),
            encoding="utf-8",
        )
        paths = ProjectPaths.from_project_root(root)
        self.context = create_module_context(
            paths, resolve_dataset(paths, "DS00", "EXP03")
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_listing_does_not_import_or_execute_module(self) -> None:
        imports: list[str] = []

        def importer(name: str) -> ModuleType:
            imports.append(name)
            return ModuleType(name)

        registry = ModuleRegistry(
            (
                ModuleDescriptor("m01", "M01", "0.1.0", "fake.m01", "run"),
            ),
            importer=importer,
        )
        self.assertEqual([item.module_id for item in registry.list_modules()], ["m01"])
        self.assertEqual(imports, [])

    def test_runner_loads_only_selected_module(self) -> None:
        imports: list[str] = []

        def importer(name: str) -> ModuleType:
            imports.append(name)
            module = ModuleType(name)
            module.run = lambda context: make_result(
                context,
                module_id="m01" if name.endswith("m01") else "m02",
                version="0.1.0",
            )
            return module

        registry = ModuleRegistry(
            (
                ModuleDescriptor("m01", "M01", "0.1.0", "fake.m01", "run"),
                ModuleDescriptor("m02", "M02", "0.1.0", "fake.m02", "run"),
            ),
            importer=importer,
        )
        result = ModuleRunner(registry).run("m01", self.context)
        self.assertEqual(result.module_id, "m01")
        self.assertEqual(imports, ["fake.m01"])

    def test_unknown_module_fails_cleanly(self) -> None:
        with self.assertRaises(UnknownModuleError):
            create_default_registry().get_module_descriptor("m99")

    def test_runner_rejects_identity_mismatch(self) -> None:
        def importer(name: str) -> ModuleType:
            module = ModuleType(name)
            module.run = lambda context: make_result(context, dataset_id="DS99")
            return module

        registry = ModuleRegistry(
            (ModuleDescriptor("m01", "M01", "0.1.0", "fake.m01", "run"),),
            importer=importer,
        )
        with self.assertRaises(ModuleIdentityError):
            ModuleRunner(registry).run("m01", self.context)

    def test_m01_production_module_is_registered_at_v11(self) -> None:
        descriptor = create_default_registry().get_module_descriptor("m01")
        self.assertEqual(descriptor.version, "1.1.0")
        self.assertIn("Drillhole Analysis", descriptor.title)


if __name__ == "__main__":
    unittest.main()
