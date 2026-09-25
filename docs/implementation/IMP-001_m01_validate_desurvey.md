# IMP-001 — M01 Validate & Desurvey

## 1. Identificación

- **Implementation ID:** IMP-001
- **Module:** M01 — Validate & Desurvey
- **Date:** 2026-09-25
- **Group:** Ejemplo docente
- **Participants:** Docente / agente de IA
- **Project:** Quebrada Verde (`quebrada_verde`)
- **Dataset / release:** `DS00` / `EXP03`
- **Audience role:** `professor_demo`
- **Status:** `IN_PROGRESS`

## 2. Problema minero

Antes de reconstruir trayectorias, posicionar intervalos o interpretar espacialmente datos de exploración, es necesario demostrar qué fuentes existen, qué representa cada campo, qué unidades emplea y cómo deben relacionarse. Una trayectoria calculada sobre identificadores inconsistentes, profundidades inválidas o convenciones angulares asumidas produciría una geometría aparentemente válida pero minéramente no defendible.

## 3. Objetivo

Dejar M01 en estado PRE-CÓDIGO mediante:

1. inventario e integridad de fuentes;
2. modelo conceptual del sistema de perforación;
3. plan de validación previo a cualquier implementación;
4. registro explícito de incertidumbres y decisiones pendientes.

No se implementan loader, validator, desurvey, geometría, visualización, modelos computacionales ni pruebas M01.

## 4. Inputs

| Fuente | Significado | Unidad | Origen | Estado / validación documental |
|---|---|---|---|---|
| `collar.csv` | Punto y orientación inicial; profundidad final | m, degree | Release `DS00/EXP03` | 42 registros; inventariado |
| `survey.csv` | Orientación downhole por profundidad medida | m, degree | Release `DS00/EXP03` | 309 registros; inventariado |
| `lithology.csv` | Intervalos litológicos observados | m | Release `DS00/EXP03` | 102 registros; inventariado |
| `alteration.csv` | Intervalos de alteración cuando estén disponibles | m | Release `DS00/EXP03` | 0 registros; header válido |
| `assay.csv` | Ensayes por intervalo | m, %, g/t | Release `DS00/EXP03` | 5,871 registros; inventariado |
| `density.csv` | Densidad por intervalo | m, t/m3 | Release `DS00/EXP03` | 464 registros; inventariado |
| `data_dictionary.csv` | Definiciones, tipos y unidades | según campo | Release `DS00/EXP03` | 54 definiciones |
| `release_manifest.json` | Identidad, campañas, conteos y hashes | — | Release `DS00/EXP03` | revisado |
| `README.md` del release | Alcance científico | — | Release `DS00/EXP03` | revisado |
| `topography/Topopl.csv` | Puntos topográficos `PID`, `X`, `Y`, `Z` | m esperados por contexto | Fuente adicional | 218,112 registros; fuera de `file_sha256` |

## 5. Outputs de esta etapa

- Inventario técnico actualizado en `docs/DATA.md`.
- Modelo conceptual actualizado en `docs/PROJECT.md` y este registro.
- Plan de validación documentado en este registro.
- Estado real actualizado en `docs/STATUS.md`.
- README alineado al estado PRE-CÓDIGO.

No se generaron outputs computacionales de M01.

Los outputs de esta etapa son documentales y no tienen unidad física propia; las unidades mineras de los inputs quedan registradas en la sección 4 y en `docs/DATA.md`.

## 6. Supuestos e incertidumbres

### Supuestos adoptados

No se adopta ningún supuesto geométrico ni umbral numérico para implementar desurvey o validación.

### Incertidumbres abiertas

- CRS/EPSG: no documentado inequívocamente.
- Convención exacta de azimuth: pendiente.
- Convención exacta de dip: pendiente.
- Método de desurvey: pendiente de definición y aprobación.
- Mapeo formal entre campañas `C01`/`C02`/`C03` del manifest y `CAMPAIGN_01`/`CAMPAIGN_02`/`CAMPAIGN_03` de los CSV: pendiente.
- Umbrales para advertencias, tolerancias y revisión minera: pendientes.
- Significado de códigos litológicos y QA/QC analítico: no documentados en la evidencia canónica revisada.

## 7. Lógica minera y modelo conceptual

```text
COLLAR
→ SURVEY
→ TRAYECTORIA 3D
→ INTERVALOS
→ POSICIÓN ESPACIAL
```

- **COLLAR** define `x`, `y`, `z`, orientación inicial y `final_depth_m`.
- **SURVEY** contiene orientaciones medidas a diferentes profundidades downhole.
- **TRAYECTORIA 3D** se calculará posteriormente con collar + survey y un método de desurvey aprobado.
- **INTERVALOS** de litología, alteración, assays y densidad se definen mediante `from_m` y `to_m`; después deberán posicionarse sobre la trayectoria.

Observación comprobada para este release: los 42 primeros registros de survey están en `depth_m = 0` y sus valores de azimuth y dip coinciden con el collar. No se generaliza este comportamiento a otros datasets.

## 8. Diseño computacional

No diseñado todavía. La próxima actividad es definir responsabilidades, contratos, flujo de datos y límites de módulos antes de crear loader o validator.

`src/` y `tests/` no contienen código M01 versionado; solo `.gitkeep`. No se agregaron dependencias.

## 9. Plan de validación — ETAPA 3

Este plan define controles conceptuales; no constituye un validator ejecutado.

### 9.1 Severidades

- **ERROR:** incumplimiento que impide usar con seguridad el registro, archivo o relación para el flujo posterior.
- **WARNING:** condición revisable que no necesariamente bloquea el procesamiento, pero puede afectar interpretación, calidad o decisión de ingeniería.
- **INFO:** hecho descriptivo, ausencia permitida o resumen útil que debe quedar trazable sin tratarse automáticamente como falla.

La asignación definitiva de severidad y cualquier tolerancia numérica deberá aprobarse durante el diseño del validator.

### 9.2 COLLAR

- `hole_id` obligatorio.
- `hole_id` único.
- `x`, `y`, `z` numéricos.
- `final_depth_m > 0`.
- `azimuth_deg` numérico y dentro del rango válido una vez aprobada su convención.
- `dip_deg` numérico y dentro del rango válido una vez aprobada su convención.
- `dataset_id`, `project_id` y campaña compatibles con la identidad del release.

### 9.3 SURVEY

- Cada `hole_id` debe existir en collar.
- `depth_m` debe ser numérica y no negativa.
- `depth_m` no debe superar `final_depth_m` del sondaje.
- Las profundidades deben poder ordenarse por sondaje.
- Detectar duplicados de `(hole_id, depth_m)`.
- `azimuth_deg` y `dip_deg` deben ser numéricos y evaluarse con convenciones aprobadas.
- Comparar el survey inicial con la orientación del collar y reportar discrepancias según una política todavía pendiente.

### 9.4 INTERVALOS

Aplicable a `lithology.csv`, `alteration.csv`, `assay.csv` y `density.csv`:

- `from_m < to_m`.
- Longitud positiva y coherencia de `length_m` cuando el campo exista.
- Intervalo contenido entre 0 y `final_depth_m`.
- `hole_id` existente en collar.
- Detección de duplicados.
- Detección de solapes cuando sean conceptualmente inválidos para la tabla.
- Reporte de gaps cuando su semántica sea pertinente; no asumir que todo gap es error.
- Nulos evaluados según el esquema y la disponibilidad real de cada fuente.
- Un archivo vacío permitido, como `alteration.csv`, debe registrarse como ausencia válida o `INFO`, no convertirse automáticamente en `ERROR`.

### 9.5 RELACIONES E IDENTIDAD

- Todos los `hole_id` referenciados deben existir en collar.
- `dataset_id` y `project_id` deben ser coherentes con el release.
- Las campañas deben ser compatibles con el manifest mediante una regla explícita y aprobada.
- Conteos y archivos deben contrastarse con el manifest.
- La integridad de bytes debe verificarse contra `file_sha256` para los archivos allí declarados.

### 9.6 TOPOGRAFÍA

- Estructura esperada: `PID`, `X`, `Y`, `Z`.
- Coordenadas numéricas.
- Detección de `PID` duplicados.
- Detección de valores nulos.
- Cobertura espacial respecto de collars como futura validación minera.
- Mantener su condición de fuente adicional fuera del manifest canónico `EXP03`.

No se fijan tolerancias de distancia, elevación o cobertura porque no están aprobadas en la evidencia canónica.

## 10. Etapas reales de trabajo

### Etapa 1 — Inventario de datos

- Se revisaron manifest, diccionario, README y archivos físicos.
- Se actualizaron identidad, rutas, campos, unidades y conteos.
- Se separó el release canónico de la topografía adicional y de los artefactos históricos.

### Etapa 2 — Modelo conceptual

- Se definió la relación COLLAR → SURVEY → TRAYECTORIA 3D → INTERVALOS → POSICIÓN ESPACIAL.
- Se mantuvieron abiertas las convenciones angulares, CRS/EPSG y método de desurvey.
- Se comprobó el comportamiento de la estación inicial de survey en los 42 sondajes sin convertirlo en regla universal.

### Etapa 3 — Plan de validación

- Se diferenciaron `ERROR`, `WARNING` e `INFO`.
- Se documentaron controles para collar, survey, intervalos, relaciones y topografía.
- No se programó ni ejecutó un validator.

### Etapa 4 — Arquitectura computacional

`PENDIENTE`. Es el siguiente paso.

## 11. Integridad e incorporación de fuentes

El 2026-09-25 se recalcularon los SHA-256 de los ocho archivos declarados en `file_sha256`; todos coincidieron. También se recalcularon los conteos físicos y coincidieron con el manifest: 42 collars, 309 surveys, 102 intervalos litológicos, 0 intervalos de alteración, 5,871 assays y 464 muestras de densidad.

`Topopl.csv` se verificó por separado: 218,112 registros, header `PID,X,Y,Z` y SHA-256 `6b150af3656c1bd7832b78e965af82ab10f48ac82126f700b740be9ff573b7f1`. No está declarado en `file_sha256` y permanece como fuente adicional.

No se modificó `data/raw/`.

## 12. Decisiones

### DECISION-01

**Problema:** cómo tratar `Topopl.csv` dentro de la trazabilidad de `EXP03`.

**Alternativas consideradas:**

- A. Incorporarlo conceptualmente al release canónico.
- B. Mantenerlo como fuente adicional explícitamente separada.

**Alternativa seleccionada:** B.

**Justificación:** el archivo existe bajo `data/raw/quebrada_verde/topography/`, pero no aparece en `file_sha256` del manifest.

**Impacto:** su estructura e integridad pueden verificarse separadamente, sin afirmar que forma parte del paquete canónico `EXP03`.

### DECISION-02

**Problema:** si los artefactos históricos locales de `outputs/quebrada_verde/` pueden cerrar T1.

**Alternativas consideradas:**

- A. Reclasificarlos como evidencia T1.
- B. Mantener T1 pendiente por falta de identidad documental suficiente.

**Alternativa seleccionada:** B.

**Justificación:** no se encontró Excel, archivo nominal T1 ni documento que vincule inequívocamente esos outputs no versionados con T1. Además, contienen resultados avanzados y supuestos fuera del alcance PRE-CÓDIGO.

**Impacto:** **T1 pendiente de incorporar al repositorio.**

### Decisiones pendientes

- Convenciones de azimuth y dip.
- CRS/EPSG.
- Método de desurvey.
- Mapeo formal de campañas.
- Política de severidades y umbrales numéricos.
- Semántica de gaps y solapes por tabla.

## 13. Archivos modificados

```text
README.md
docs/PROJECT.md
docs/DATA.md
docs/STATUS.md
docs/implementation/IMP-001_m01_validate_desurvey.md
```

No se modificaron archivos de gobernanza ni datos fuente.

## 14. Verificaciones y pruebas realizadas

### Inspección y fuentes

- `git status --short --branch`: ejecutado; rama `main`; se observaron únicamente los conjuntos históricos no versionados ya identificados.
- `git remote -v`: ejecutado; `origin` apunta a `https://github.com/DDev1822/PlanMinMaster.git`.
- `git log -8 --oneline --decorate`: ejecutado; se revisó el historial reciente.
- Lectura de gobernanza y documentación requerida: ejecutada.
- Inspección de `data/raw/`, `data/processed/`, `outputs/`, `src/` y `tests/`: ejecutada.
- Recuento mediante `Import-Csv`: ejecutado para los CSV canónicos y la topografía.
- Recálculo mediante `Get-FileHash -Algorithm SHA256`: ejecutado; 8/8 hashes declarados coincidieron.
- Revisión del primer survey por sondaje: ejecutada; 42/42 a profundidad 0 y 42/42 coincidentes con la orientación del collar.
- Búsqueda con `rg` y listado de hojas de cálculo/T1: ejecutada; no se encontró evidencia identificada como T1.

### Validaciones finales del cambio documental

- `git diff --check`: ejecutado; sin errores de whitespace. Git informó únicamente advertencias esperadas de conversión LF/CRLF en Windows.
- `git diff -- README.md docs/PROJECT.md docs/DATA.md docs/STATUS.md docs/implementation/IMP-001_m01_validate_desurvey.md`: ejecutado y revisado.
- Búsqueda del listado solicitado de referencias obsoletas en los cinco documentos autorizados: sin coincidencias.
- `git ls-files src tests`: ejecutado; únicamente `src/.gitkeep` y `tests/.gitkeep`.
- `git ls-files data/raw`: ejecutado; se confirmó el release canónico y la topografía versionados.
- `git diff --name-only -- data/raw`: ejecutado; sin cambios.
- Revisión de archivos de gobernanza mediante `git diff --name-only`: ejecutada; sin cambios.
- Revisión de dependencias: ejecutada; sin cambios en `requirements.txt`, `pyproject.toml`, `package.json` ni `package-lock.json`.

### Pruebas de software M01

- **Status:** `NOT RUN`
- **Tests passed:** 0
- **Tests failed:** 0

No existe código M01 nuevo que probar. Las comprobaciones anteriores son inspecciones documentales y de integridad de fuentes, no pruebas del futuro software.

## 15. Validación minera

No corresponde declarar validación minera final de resultados computacionales porque no se ha implementado loader, validator ni desurvey. En esta etapa sí se verificaron identidad, unidades documentadas, relaciones conceptuales, conteos e integridad de las fuentes.

## 16. Limitaciones, pendientes y uso de IA

### Limitaciones y pendientes

- Arquitectura computacional no diseñada.
- Loader, validator, desurvey y visualización no implementados.
- Pruebas computacionales y validación minera de resultados: pendientes.
- Convenciones geométricas, CRS/EPSG, mapeo de campañas y umbrales: pendientes.
- **T1 pendiente de incorporar al repositorio.**

### Uso del agente de IA

- [x] Inspección de fuentes y trazabilidad.
- [x] Revisión de unidades e identidad.
- [x] Documentación del modelo conceptual.
- [x] Documentación del plan de validación.
- [ ] Arquitectura.
- [ ] Algoritmo.
- [ ] Implementación.
- [ ] Pruebas de software.
- [ ] Depuración.

## 17. Checklist de cierre del módulo

- [x] Problema minero documentado.
- [x] Inputs inventariados.
- [x] Unidades disponibles registradas.
- [x] Supuestos e incertidumbres identificados.
- [x] Lógica minera conceptual documentada.
- [ ] Arquitectura definida.
- [ ] Implementación terminada.
- [ ] Pruebas de software ejecutadas.
- [ ] Validación computacional realizada.
- [ ] Validación minera final realizada.
- [x] Archivos modificados registrados.
- [x] Limitaciones registradas.
- [x] Registro actualizado al estado actual.

**Status permanece `IN_PROGRESS`.**
