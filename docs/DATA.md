# DATA.md

Inventario técnico del ejemplo docente **Cerro Azul — DS01 — EXP03**.

## Reglas

- `data/raw/` es inmutable.
- No inventar campos, unidades, procedencia ni valores.
- Esta documentación registra lo observado en la ETAPA 1; no sustituye los archivos fuente.

## Inventario observado

| Archivo | Función minera preliminar | Registros | Clave / identificador | Observaciones |
|---|---|---:|---|---|
| `collar.csv` | Boca, posición inicial, orientación inicial y profundidad final | 32 | `hole_id` | 32 sondajes |
| `survey.csv` | Orientación downhole | 208 | `(hole_id, depth_m)` | Todos los sondajes tienen survey |
| `lithology.csv` | Intervalos litológicos | 95 | `(hole_id, from_m, to_m)` | AIR, BRX, DIO, POR, REG observados |
| `alteration.csv` | Alteración por intervalo | 0 | — | Vacío según el release |
| `assay.csv` | Resultados analíticos | 3,619 | `sample_id` | Cu variable; Mo y Au observados en cero |
| `density.csv` | Muestras de densidad | 290 | `density_sample_id` | Intervalos de 1 m observados |
| `data_dictionary.csv` | Campos, tipos y unidades | 54 definiciones | tabla + campo | No define convenciones angulares |
| `release_manifest.json` | Identidad, campañas, conteos e integridad | 1 | dataset / release | Conteos y hashes reportados coherentes |
| `README.md` | Alcance del release | documento | — | Datos sintéticos; sistema cartesiano local |

## Resumen

- Campañas: CAMPAIGN_01, CAMPAIGN_02, CAMPAIGN_03
- Sondajes: 32
- Survey: 208
- Litología: 95 intervalos
- Alteración: 0 intervalos
- Ensayes: 3,619
- Densidad: 290 muestras
- Datos sintéticos: sí
- Declaración de recursos/reservas: no

## Unidades observadas

| Familia | Unidad |
|---|---|
| X, Y, Z, profundidades, FROM, TO, LENGTH | m |
| Azimuth, dip | degree |
| Cu, Mo | percent |
| Au | g/t |
| Density | t/m3 |

## Incertidumbres abiertas

- CRS / EPSG: UNKNOWN
- Convención exacta de azimuth: PENDIENTE
- Convención exacta de dip: PENDIENTE
- Método de desurvey: PENDIENTE
- Significado de códigos litológicos: NO DOCUMENTADO
- QA/QC analítico: NO DOCUMENTADO
- Estrategia de densidad: PENDIENTE

## Fuente física

Los archivos reales DS01/EXP03 no se reconstruyen a partir de este inventario. Deben copiarse desde el release original del docente a `data/raw/`.
