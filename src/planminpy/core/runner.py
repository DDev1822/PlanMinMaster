"""Execute exactly one selected module through the common contract."""

from __future__ import annotations

from planminpy.core.context import ModuleContext
from planminpy.core.contracts import ModuleResult, PlanMinPyError
from planminpy.core.registry import ModuleAvailability, ModuleRegistry, ModuleUnavailableError


class ModuleExecutionError(PlanMinPyError):
    """Raised when a module cannot satisfy the execution contract."""


class ModuleIdentityError(ModuleExecutionError):
    """Raised when returned identity differs from the selected context."""


class ModuleRunner:
    def __init__(self, registry: ModuleRegistry) -> None:
        self._registry = registry

    def run(self, module_id: str, context: ModuleContext) -> ModuleResult:
        descriptor = self._registry.get_module_descriptor(module_id)
        if descriptor.availability is not ModuleAvailability.AVAILABLE:
            raise ModuleUnavailableError(f"module {module_id} is not implemented")
        module_callable = self._registry.load_module(module_id)
        try:
            result = module_callable(context)
        except PlanMinPyError:
            raise
        except Exception as exc:
            raise ModuleExecutionError(
                f"module {module_id} failed during execution: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if not isinstance(result, ModuleResult):
            raise ModuleExecutionError(
                f"module {module_id} must return a ModuleResult"
            )

        expected_identity = {
            "module_id": descriptor.module_id,
            "project_id": context.project_id,
            "dataset_id": context.dataset_id,
            "release_id": context.release_id,
        }
        for field_name, expected in expected_identity.items():
            actual = getattr(result, field_name)
            if actual != expected:
                raise ModuleIdentityError(
                    f"module result {field_name} mismatch: "
                    f"expected {expected!r}, got {actual!r}"
                )
        if result.module_version != descriptor.version:
            raise ModuleIdentityError(
                "module result version mismatch: "
                f"expected {descriptor.version!r}, got {result.module_version!r}"
            )
        return result
