"""Central lazy registry for independently executable mining modules."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from enum import Enum
from types import ModuleType
from typing import Any, Callable, Iterable

from planminpy.core.contracts import (
    ModuleCallable,
    PlanMinPyError,
    validate_identifier,
)


class ModuleRegistryError(PlanMinPyError):
    """Base class for controlled registry failures."""


class UnknownModuleError(ModuleRegistryError):
    """Raised when a requested module ID is not registered."""


class ModuleLoadError(ModuleRegistryError):
    """Raised when a lazy module entry cannot be imported or called."""


class ModuleUnavailableError(ModuleRegistryError):
    """Raised when a registered roadmap module is not executable."""


class ModuleAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass(frozen=True)
class ModuleDescriptor:
    module_id: str
    title: str
    version: str
    import_path: str
    callable_name: str
    description: str = ""
    availability: ModuleAvailability = ModuleAvailability.AVAILABLE
    wizard_import_path: str | None = None
    wizard_callable_name: str | None = None

    def __post_init__(self) -> None:
        validate_identifier("module_id", self.module_id)
        for field_name in ("title", "version", "import_path", "callable_name"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ModuleRegistryError(f"{field_name} must be a non-empty string")
        if not isinstance(self.description, str):
            raise ModuleRegistryError("description must be a string")
        if not isinstance(self.availability, ModuleAvailability):
            raise ModuleRegistryError("availability must be a ModuleAvailability value")
        wizard_fields = (self.wizard_import_path, self.wizard_callable_name)
        if any(value is not None for value in wizard_fields) and not all(
            isinstance(value, str) and value.strip() for value in wizard_fields
        ):
            raise ModuleRegistryError(
                "wizard_import_path and wizard_callable_name must be configured together"
            )


class ModuleRegistry:
    def __init__(
        self,
        descriptors: Iterable[ModuleDescriptor],
        *,
        importer: Callable[[str], ModuleType] = importlib.import_module,
    ) -> None:
        self._descriptors: dict[str, ModuleDescriptor] = {}
        for descriptor in descriptors:
            if descriptor.module_id in self._descriptors:
                raise ModuleRegistryError(
                    f"duplicate module registration: {descriptor.module_id}"
                )
            self._descriptors[descriptor.module_id] = descriptor
        self._importer = importer

    def list_modules(self) -> tuple[ModuleDescriptor, ...]:
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))

    def get_module_descriptor(self, module_id: str) -> ModuleDescriptor:
        try:
            return self._descriptors[module_id]
        except KeyError as exc:
            raise UnknownModuleError(f"unknown module ID: {module_id}") from exc

    def load_module(self, module_id: str) -> ModuleCallable:
        descriptor = self.get_module_descriptor(module_id)
        if descriptor.availability is not ModuleAvailability.AVAILABLE:
            raise ModuleUnavailableError(f"module {module_id} is not implemented")
        try:
            imported = self._importer(descriptor.import_path)
            module_callable = getattr(imported, descriptor.callable_name)
        except (ImportError, AttributeError) as exc:
            raise ModuleLoadError(
                f"cannot load {module_id} from "
                f"{descriptor.import_path}:{descriptor.callable_name}"
            ) from exc
        if not callable(module_callable):
            raise ModuleLoadError(
                f"registered target is not callable for module {module_id}"
            )
        return module_callable

    def load_wizard(self, module_id: str) -> Any:
        descriptor = self.get_module_descriptor(module_id)
        if descriptor.availability is not ModuleAvailability.AVAILABLE:
            raise ModuleUnavailableError(f"module {module_id} is not implemented")
        if descriptor.wizard_import_path is None or descriptor.wizard_callable_name is None:
            raise ModuleLoadError(f"module {module_id} does not provide an interactive wizard")
        try:
            imported = self._importer(descriptor.wizard_import_path)
            factory = getattr(imported, descriptor.wizard_callable_name)
            wizard = factory()
        except (ImportError, AttributeError, TypeError) as exc:
            raise ModuleLoadError(
                f"cannot load wizard for {module_id} from "
                f"{descriptor.wizard_import_path}:{descriptor.wizard_callable_name}"
            ) from exc
        if not callable(getattr(wizard, "interact", None)) or not callable(
            getattr(wizard, "show_result", None)
        ):
            raise ModuleLoadError(
                f"wizard for {module_id} must provide interact() and show_result()"
            )
        return wizard


def create_default_registry() -> ModuleRegistry:
    return ModuleRegistry(
        (
            ModuleDescriptor(
                module_id="m01",
                title="M01 — Validate, Desurvey & Drillhole Analysis",
                version="1.1.0",
                import_path="planminpy.modules.m01.module",
                callable_name="run",
                description=(
                    "Validate source data, calculate continuous drillhole geometry, "
                    "position assays, and analyze the complete observed grade distribution."
                ),
                wizard_import_path="planminpy.modules.m01.wizard",
                wizard_callable_name="create_wizard",
            ),
        )
    )
