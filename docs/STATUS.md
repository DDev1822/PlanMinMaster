# STATUS.md

## Estado actual

- **Último IMP cerrado:** Ninguno
- **Módulo en desarrollo:** M01 — Validate & Desurvey
- **Estado:** `IN_PROGRESS`
- **Etapa alcanzada:** ETAPA 3 — PLAN DE VALIDACIÓN DOCUMENTADO
- **Fecha de actualización:** 2026-09-25

## Módulos

| IMP | Módulo | Estado | Observación |
|---|---|---|---|
| IMP-001 | M01 — Validate & Desurvey | `IN_PROGRESS` | Etapas 1, 2 y 3 documentadas; sin implementación M01 |

## Completado con evidencia

- Incorporación del dataset canónico Quebrada Verde `DS00/EXP03` en `data/raw/`.
- Inventario técnico de los archivos del release y de la topografía adicional.
- Recuento físico de registros y contraste con `release_manifest.json`.
- Recálculo de los ocho SHA-256 declarados en `file_sha256`: todos coinciden.
- Documentación del modelo conceptual COLLAR → SURVEY → TRAYECTORIA 3D → INTERVALOS → POSICIÓN ESPACIAL.
- Documentación previa del plan de validación con categorías `ERROR`, `WARNING` e `INFO`.

## Pendiente

- ETAPA 4 — arquitectura computacional.
- Loader.
- Validator.
- Pruebas computacionales de M01.
- Desurvey y aprobación de su método.
- Visualización.
- Validación minera de resultados computacionales.
- Definición o aprobación de convenciones de azimuth y dip, CRS/EPSG, mapeo de campañas y umbrales numéricos.
- **T1 pendiente de incorporar al repositorio.**

## Evidencia T1

La búsqueda en `outputs/`, `outputs/tables/`, documentos y archivos de hoja de cálculo no encontró una evidencia identificada como T1 ni un Excel de auditoría. Existen artefactos avanzados históricos dentro de `outputs/quebrada_verde/`, pero son locales, no versionados, proceden del desarrollo anterior y contienen supuestos e implementación que están fuera del alcance PRE-CÓDIGO; por tanto, no se reclasifican como evidencia T1 ni sustentan el cierre de esta etapa.

## Código M01

No se creó código M01. Los únicos archivos versionados bajo `src/` y `tests/` continúan siendo sus respectivos `.gitkeep`; `main.py` conserva únicamente el entry point inicial.

## Próximo paso

**ETAPA 4 — ARQUITECTURA COMPUTACIONAL**, antes de implementar loader y validator.

M01 no está cerrado.
