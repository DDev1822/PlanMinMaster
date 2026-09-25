# PROJECT.md

## Identificación

- **Grupo:** Ejemplo docente
- **Proyecto / depósito:** Quebrada Verde
- **Project ID:** `quebrada_verde`
- **Dataset:** `DS00`
- **Release:** `EXP03`
- **Audience role:** `professor_demo`
- **Tipo:** exploración
- **Curso:** Planeamiento de Minado — MINN1508A
- **Periodo:** 2026-2
- **Estado:** M01 `IN_PROGRESS`

## Problema minero

Los datos de collar, orientación downhole e intervalos no pueden interpretarse espacialmente de forma confiable sin comprender antes su identidad, unidades, relaciones, restricciones e incertidumbres. El proyecto debe preparar una base verificable para reconstruir posteriormente las trayectorias 3D y posicionar los intervalos sin inventar convenciones geométricas.

## Objetivo actual

Cerrar el estado pedagógico PRE-CÓDIGO de M01 mediante:

1. inventario e integridad de las fuentes;
2. modelo conceptual del sistema de perforación;
3. plan de validación previo a la implementación.

La secuencia minera que deberá soportar una implementación posterior es:

```text
COLLAR
→ SURVEY
→ TRAYECTORIA 3D
→ INTERVALOS
→ POSICIÓN ESPACIAL
```

## Modelo conceptual del sistema de perforación

### COLLAR

Define el punto inicial del sondaje mediante `x`, `y`, `z`, su orientación inicial mediante `azimuth_deg` y `dip_deg`, y el límite de profundidad medida mediante `final_depth_m`.

### SURVEY

Registra mediciones de orientación (`azimuth_deg`, `dip_deg`) a profundidades medidas (`depth_m`) a lo largo de cada `hole_id`.

En este release, una comprobación de los 42 sondajes encontró que el primer registro de survey está en `depth_m = 0` y reproduce la orientación inicial del collar. Este es un hecho observado de `DS00/EXP03`; no se adopta como regla universal para otros datasets.

### TRAYECTORIA 3D

Se obtendrá posteriormente combinando collar y survey mediante un método de desurvey todavía pendiente de definición y aprobación. En esta etapa no se calculan coordenadas ni trayectorias.

### INTERVALOS

`lithology.csv`, `alteration.csv`, `assay.csv` y `density.csv` representan información por intervalos de profundidad downhole. En una fase posterior, sus extremos o puntos representativos deberán posicionarse sobre la trayectoria 3D del sondaje correspondiente.

## Alcance actual

- Inventario de fuentes: documentado.
- Integridad de los archivos declarados por el manifest: comprobada.
- Modelo conceptual: documentado.
- Plan de validación: documentado.
- Arquitectura computacional: pendiente.
- Implementación M01 y pruebas de software: no iniciadas.

## Incertidumbres y decisiones abiertas

- CRS/EPSG: no está inequívocamente documentado.
- Convención exacta de azimuth: pendiente de aprobación.
- Convención exacta de dip: pendiente de aprobación.
- Método de desurvey: pendiente de definición y aprobación.
- Correspondencia formal entre campañas `C01`/`C02`/`C03` del manifest y `CAMPAIGN_01`/`CAMPAIGN_02`/`CAMPAIGN_03` observadas en los CSV: pendiente de documentar o aprobar.
- Umbrales numéricos para warnings o revisión: pendientes; no se inventan en esta etapa.
- Significado de códigos litológicos y QA/QC analítico: no documentados en la evidencia canónica revisada.

## Restricciones

- `data/raw/` es inmutable.
- Los datos son sintéticos y educativos.
- El release contiene observaciones de exploración y no constituye una declaración de recursos o reservas.
- M01 permanece `IN_PROGRESS`.
