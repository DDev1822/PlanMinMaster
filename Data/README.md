# Project data

Place project exploration datasets and topography inputs in this directory.

An exploration dataset directory uses the current M01 source contract:

```text
release_manifest.json
collar.csv
survey.csv
assay.csv
lithology.csv
alteration.csv
density.csv
```

Optional supporting files may include `data_dictionary.csv` and `README.md`.

Topography is supplied as a CSV with the exact fields:

```text
PID,X,Y,Z
```

PlanMinPy discovers schema-valid exploration datasets and topography files automatically. Source inputs are immutable during execution; generated artifacts are written under `outputs/`.
