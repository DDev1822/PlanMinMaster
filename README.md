# PlanMinMaster

Repositorio de **ejemplo docente** para **Planeamiento de Minado — UPN 2026-2**.

La rama `main` conserva el estado pedagógico **PRE-CÓDIGO de M01 — Validate & Desurvey**: primero se comprende la información minera, luego se define el modelo y el plan de validación, y recién después se diseña la arquitectura computacional.

## Estado actual

```text
Repositorio y gobernanza configurados
→ Dataset docente DS00/EXP03 incorporado
→ ETAPA 1 — INVENTARIO DE DATOS completada
→ ETAPA 2 — MODELO CONCEPTUAL documentado
→ ETAPA 3 — PLAN DE VALIDACIÓN documentado
→ ETAPA 4 — ARQUITECTURA COMPUTACIONAL siguiente
→ sin loader
→ sin validator
→ sin desurvey
→ sin visualizer
```

## Ejemplo docente

- **Proyecto / depósito:** Quebrada Verde
- **Project ID:** `quebrada_verde`
- **Dataset:** `DS00`
- **Release:** `EXP03`
- **Audience role:** `professor_demo`
- **Tipo:** exploración
- **Campañas declaradas por el manifest:** `C01`, `C02`, `C03`
- **Naturaleza:** datos sintéticos educativos
- **Declaración de recursos o reservas:** no
- **Estado M01:** `IN_PROGRESS`

La trazabilidad del trabajo se mantiene en [docs/implementation/IMP-001_m01_validate_desurvey.md](docs/implementation/IMP-001_m01_validate_desurvey.md).

## Datos fuente

El release canónico se encuentra en:

```text
data/raw/quebrada_verde/DS00/EXP03/
```

La topografía `data/raw/quebrada_verde/topography/Topopl.csv` es una fuente adicional: no forma parte de los archivos declarados en `file_sha256` por el manifest de `EXP03`.

Los archivos de `data/raw/` son inmutables. Los elementos históricos locales no versionados (`data/PL00/`, `data/Topopl.csv` y `outputs/quebrada_verde/`) quedan fuera del alcance y no forman parte de este estado pedagógico.

## Principio

> **Primero minería. Después algoritmo. Después código.**

La implementación avanzada histórica se conserva en `archive/m01-advanced-before-session2-reset`; no debe usarse como solución anticipada para estudiantes.

## Próxima actividad

Diseñar la arquitectura computacional de M01 a partir del modelo conceptual y del plan de validación ya documentados. Todavía no corresponde implementar loader, validator, desurvey ni visualización.

**T1 pendiente de incorporar al repositorio.**
