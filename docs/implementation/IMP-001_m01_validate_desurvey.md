# IMP-001 — M01 Validate & Desurvey

## 1. Identificación

- **Implementation ID:** IMP-001
- **Module:** M01 — Validate & Desurvey
- **Date:** 2026-09-19
- **Group:** Ejemplo docente
- **Participants:** Docente / agente de IA
- **Status:** IN_PROGRESS

## 2. Problema minero

Antes de reconstruir trayectorias, posicionar muestras o interpretar espacialmente los datos de exploración, es necesario conocer qué archivos existen, qué representa cada uno, qué unidades utilizan y cómo se relacionan.

Todavía no se implementa validator ni desurvey.

## 3. Objetivo

Documentar el inventario real reportado para DS01/EXP03 y dejar explícitas las incertidumbres que deben resolverse antes de diseñar validación y desurvey.

## 4. Inputs

| Archivo | Significado preliminar | Unidad | Estado |
|---|---|---|---|
| collar.csv | Collars | m / degree | Inventariado |
| survey.csv | Survey downhole | m / degree | Inventariado |
| lithology.csv | Intervalos litológicos | m | Inventariado |
| alteration.csv | Alteración | m | 0 registros |
| assay.csv | Ensayes | m, %, g/t | Inventariado |
| density.csv | Densidad | m, t/m3 | Inventariado |
| data_dictionary.csv | Diccionario | — | Inventariado |
| release_manifest.json | Identidad y conteos | — | Inventariado |
| README.md | Descripción del release | — | Inventariado |

## 5. Outputs

- Inventario técnico: `docs/DATA.md`.
- Incertidumbres abiertas: este IMP.
- Estado del módulo: `docs/STATUS.md`.

## 6. Supuestos

No se adopta todavía ningún supuesto geométrico para desurvey.

Pendientes: CRS/EPSG, convención de azimuth, convención de dip, método de desurvey, significado de códigos litológicos, estrategia de densidad y QA/QC analítico.

## 7. Lógica minera

Relación conceptual preliminar, todavía no desarrollada en profundidad:

```text
HOLE_ID
→ COLLAR
→ SURVEY
→ TRAYECTORIA 3D
→ INTERVALOS
→ POSICIÓN ESPACIAL DE LAS MUESTRAS
```

La ETAPA 2 debe enseñar y comprobar esta relación antes de implementar.

## 8. Diseño computacional

No se ha diseñado todavía la arquitectura M01.

No existen funciones ni clases M01 en esta rama pedagógica.

No se agregaron dependencias para M01.

## 9. Etapas de implementación

### Etapa 1 — Inventario de datos

- **Objetivo:** comprender el release antes de programar.
- **Trabajo realizado:** inspección de los archivos reportados; revisión de manifiesto, diccionario y README; identificación de campos, unidades, claves, relaciones y dudas.
- **Resultado:** inventario registrado en `docs/DATA.md`.
- **Pendiente:** ETAPA 2 — Modelo conceptual.

### Nota de trazabilidad

Este registro se incorpora al preparar el repositorio maestro en su estado pedagógico pre-sesión 2. Resume únicamente evidencia realmente obtenida en la ETAPA 1; no declara implementación, pruebas ni validaciones inexistentes.

## 10. Decisiones

Todavía no se ha aprobado una decisión de ingeniería para convenciones geométricas, método de desurvey ni umbrales del validator.

## 11. Archivos creados o modificados

```text
README.md
docs/PROJECT.md
docs/DATA.md
docs/STATUS.md
docs/implementation/IMP-001_m01_validate_desurvey.md
```

La gobernanza se sincronizó con PlanMinUPN por autorización docente.

## 12. Pruebas realizadas

- **Status:** NOT RUN
- **Tests passed:** 0
- **Tests failed:** 0

No existe todavía código M01 que probar.

## 13. Validación minera

Todavía no corresponde declarar validación minera de resultados. Solo se ha completado el inventario técnico inicial.

## 14. Limitaciones y pendientes

- Los archivos fuente DS01/EXP03 deben incorporarse desde la fuente original; no se reconstruyen.
- CRS/EPSG no está documentado.
- Siguiente: ETAPA 2.
- Después: ETAPA 3.

## 15. Uso del agente de IA

- [x] Explicación conceptual.
- [ ] Arquitectura.
- [ ] Algoritmo.
- [ ] Implementación.
- [ ] Pruebas.
- [ ] Depuración.
- [x] Revisión de unidades.
- [x] Documentación.

## 16. Checklist de cierre

- [x] Problema minero inicial documentado.
- [x] Inputs inventariados.
- [x] Unidades disponibles registradas.
- [x] Incertidumbres identificadas.
- [ ] Lógica minera completa documentada.
- [ ] Implementación terminada.
- [ ] Pruebas finales ejecutadas.
- [ ] Validación computacional realizada.
- [ ] Validación minera realizada.
- [x] Limitaciones registradas.
- [x] Registro actualizado al estado actual.

**Status permanece IN_PROGRESS.**
