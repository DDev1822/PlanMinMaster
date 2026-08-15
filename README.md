# PlanMinMaster

Educational modular mine-planning engine used in the Planeamiento de Minado course.

The currently implemented module is:

```text
M01 — Validate, Desurvey & Drillhole Analysis
```

M01 follows this functional flow:

```text
LOAD
→ VALIDATE
→ DESURVEY
→ POSITION ASSAYS IN 3D
→ OBSERVED GRADE DISTRIBUTION
→ OPTIONAL REFERENCE-GRADE INTERCEPTS
→ 3D VISUALIZATION
→ TECHNICAL SUMMARY
→ DATAMINE EXPORT
```

M01 does not calculate Mineral Resources or Mineral Reserves.

## Architecture

PlanMinMaster keeps application orchestration separate from module science:

```text
main.py
→ interactive dashboard
→ module registry
→ module-specific wizard
→ runner
→ reporter
```

Modules execute independently through the shared application contracts. The reporter consumes normalized module results and replaces the corresponding report section when a module is rerun.

## Data

Place exploration datasets and topography inputs under:

```text
Data/
```

PlanMinPy automatically discovers schema-valid exploration releases and topography CSV files. Teaching and project datasets are intentionally not included in this repository; see `Data/README.md` for the expected layout.

Generated runtime artifacts are written only under `outputs/`, which is excluded from version control.

## Installation

Python 3.12 is required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

## Execution

Start the interactive dashboard:

```powershell
python main.py
```

List registered modules or run M01 directly:

```powershell
python main.py list
python main.py run m01 --dataset <dataset_id> --release <release_id>
```

The direct M01 command requires one uniquely discoverable schema-valid topography CSV inside `Data/`. Use the interactive dashboard when multiple candidates exist.

## Datamine interoperability

M01 always produces deterministic Datamine-ready staging packages. Genuine native `.dm` drillhole and PT/TR wireframe files are generated when a compatible registered Datamine backend is installed. The application never renames CSV files to imitate native Datamine files.

## Tests

Run the complete unit suite with:

```powershell
python -m unittest discover -s tests -v
```
