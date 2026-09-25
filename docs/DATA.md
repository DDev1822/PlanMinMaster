# DATA.md

Inventario técnico del ejemplo docente **Quebrada Verde — DS00 — EXP03**.

## Identidad de la fuente

- **Ruta canónica:** `data/raw/quebrada_verde/DS00/EXP03/`
- **Project ID:** `quebrada_verde`
- **Dataset ID:** `DS00`
- **Release ID:** `EXP03`
- **Audience role:** `professor_demo`
- **Release type:** `exploration`
- **Campañas declaradas por el manifest:** `C01`, `C02`, `C03`
- **Datos sintéticos educativos:** sí
- **Declaración de recursos o reservas:** no

## Reglas

- `data/raw/` es inmutable.
- No inventar campos, unidades, procedencia, convenciones ni valores.
- Distinguir el release canónico de las fuentes adicionales y de los artefactos históricos locales no versionados.

## Inventario observado

| Archivo | Función minera / documental | Registros | Campos principales | Clave / identificador |
|---|---|---:|---|---|
| `collar.csv` | Boca, coordenadas, orientación inicial y profundidad final | 42 | `hole_id`, `x`, `y`, `z`, `azimuth_deg`, `dip_deg`, `final_depth_m` | `hole_id` |
| `survey.csv` | Orientación downhole por profundidad medida | 309 | `hole_id`, `depth_m`, `azimuth_deg`, `dip_deg` | `(hole_id, depth_m)` |
| `lithology.csv` | Intervalos litológicos | 102 | `hole_id`, `from_m`, `to_m`, `length_m`, `lith_code` | intervalo por sondaje |
| `alteration.csv` | Alteración por intervalo | 0 | header válido con `hole_id`, `from_m`, `to_m`, `length_m`, códigos e intensidad | sin registros; alteración no disponible en esta versión |
| `assay.csv` | Resultados analíticos por intervalo | 5,871 | `sample_id`, `hole_id`, `from_m`, `to_m`, `length_m`, `cu_pct`, `mo_pct`, `au_gt` | `sample_id` |
| `density.csv` | Muestras de densidad por intervalo | 464 | `density_sample_id`, `hole_id`, `from_m`, `to_m`, `length_m`, `density_t_m3` | `density_sample_id` |
| `data_dictionary.csv` | Definiciones, tipos, nulabilidad y unidades | 54 definiciones | `file`, `column`, `description`, `unit`, `dtype`, `nullable` | `(file, column)` |
| `release_manifest.json` | Identidad, campañas, conteos e integridad | 1 documento | metadatos, conteos, lista de archivos y `file_sha256` | dataset / release |
| `README.md` | Alcance científico del release | 1 documento | contenidos, unidades y limitación científica | — |

## Topografía adicional

| Archivo | Registros | Campos observados | Unidad espacial esperada | Relación con EXP03 |
|---|---:|---|---|---|
| `data/raw/quebrada_verde/topography/Topopl.csv` | 218,112 | `PID`, `X`, `Y`, `Z` | m, según el contexto del proyecto | Fuente adicional; no está incluida en `file_sha256` del manifest |

El SHA-256 observado para esta fuente adicional el 2026-09-25 fue `6b150af3656c1bd7832b78e965af82ab10f48ac82126f700b740be9ff573b7f1`. Se registra para trazabilidad local, sin convertir el archivo en parte canónica del release `EXP03`.

## Unidades observadas

| Familia | Unidad documentada |
|---|---|
| Coordenadas `x`, `y`, `z`; profundidades; `from_m`; `to_m`; `length_m` | m |
| Azimuth y dip | degree |
| Cu y Mo | percent |
| Au | g/t |
| Densidad | t/m3 |

## Identidad y campañas observadas en los CSV

Los CSV con registros contienen `dataset_id = DS00` y `project_id = quebrada_verde`. En ellos se observaron `CAMPAIGN_01`, `CAMPAIGN_02` y `CAMPAIGN_03`, mientras que el manifest declara `C01`, `C02` y `C03`. La correspondencia parece nominalmente compatible, pero su mapeo formal queda **PENDIENTE DE APROBACIÓN** y no se codifica como supuesto en esta etapa. `alteration.csv` no aporta valores de identidad porque tiene cero registros válidos.

## Integridad de fuentes

Comprobación ejecutada el **2026-09-25**:

- los ocho archivos declarados en `file_sha256` existen dentro del release;
- se recalculó SHA-256 para cada uno y los ocho valores coincidieron con el manifest;
- los conteos físicos recalculados coinciden con los conteos declarados: 42 collars, 309 surveys, 102 intervalos litológicos, 0 intervalos de alteración, 5,871 assays y 464 muestras de densidad;
- `alteration.csv` conserva un header válido aunque no tenga registros;
- `Topopl.csv` se comprobó separadamente con 218,112 registros y no forma parte de `file_sha256`;
- no se modificó ningún archivo dentro de `data/raw/`.

El propio `release_manifest.json` no se declara a sí mismo dentro de `file_sha256`; la afirmación de coincidencia se limita estrictamente a los ocho archivos allí enumerados.

## Incertidumbres abiertas

- CRS / EPSG: `PENDIENTE`.
- Convención exacta de azimuth: `PENDIENTE`.
- Convención exacta de dip: `PENDIENTE`.
- Método de desurvey: `PENDIENTE`.
- Mapeo formal de identificadores de campaña: `PENDIENTE`.
- Significado de códigos litológicos: `NO DOCUMENTADO`.
- QA/QC analítico: `NO DOCUMENTADO`.
- Criterios operacionales para gaps, solapes y tolerancias numéricas: `PENDIENTES`.
