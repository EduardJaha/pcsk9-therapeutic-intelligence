# Integrated discovery workbench

Implemented on 22 October 2026 following hands-on research of
[KMed](https://kmed.boraarifi.ai/) and its upstream scientific tools. This is an
independent implementation in our existing FastAPI/Streamlit application. It
does not copy KMed source or claim equivalent scientific performance.

## What is available

| Page | Use | Evidence status |
|---|---|---|
| Molecule dossier | Enter SMILES; inspect 13 calculated properties, 2D structure, PAINS/BRENK flags and Lipinski checks; generate a rotatable 3D conformer and export SDF. Carry the selected structure into prediction, docking or design. | RDKit calculations and heuristics; no activity or safety claim. |
| Endpoint predictions | Register the installed experimental ADMET release; choose up to 50 distinct molecules and any of nine endpoints; queue local inference; inspect/download individual results. | Real pretrained inference, not independently evaluated for this workspace. Unknown calibration, applicability and training overlap remain explicit. |
| Target biology | Enter a public human Ensembl identifier; optionally supply a PDB ID; retrieve disease associations and structure metadata. | Public source snapshots retained with response hashes and timestamps when explicitly saved. PDB/target compatibility is not inferred. |
| Structure & docking | Supply ligand SMILES, a prepared rigid receptor PDBQT, source, preparation notes and pocket rationale; specify grid, seed and exhaustiveness; queue Vina and inspect/export poses. | Local structure-based hypotheses; no measured affinity, receptor approval or PCSK9 activity inferred. |
| Assay analysis | Fit a four-parameter concentration-response curve with explicit units/direction, retained replicates, residuals and quality flags; calculate Z-prime from controls. | Unreviewed numerical analysis. Optional run/sample linkage checks project, material origin and modality. No training measurements are inserted. |
| SAR & design | Screen up to 500 structures; examine same-assay activity cliffs from up to 100 observations; enumerate selected chemical transformations and a diverse shortlist. | Structural similarity, descriptive SAR and proposals. No validated MMP attribution, synthetic route, potency improvement or active-learning claim. |
| Research runs | Inspect saved analyses, jobs, model manifests, original inputs, hashes and failures; export JSON; retry a failed job as a new run. | Durable local research history with explicit project scope. |

All new molecular forms begin blank. Carrying a molecule between pages is an
explicit action. The new dossier accepts acyclic small molecules; the existing
PCSK9 training/profile pipeline retains its ring-scaffold restriction.

## Start the application

From the repository root, use the existing environment or:

```sh
uv sync --frozen --extra dev
.venv/bin/cvti start
```

`cvti start` runs the API, Streamlit and one local worker. If launching services
separately, also run `.venv/bin/cvti worker`. Scientific jobs are queued and then
processed by that worker. Use **Refresh run status** or **Research runs** to
inspect completion. Refreshing a page never resubmits a calculation.

The additive `f51d7a64b208` migration adds `discovery_models` and
`discovery_runs`. Existing measurements, observations, curated datasets,
evaluation assignments and models retain their previous meanings. Back up an
existing workspace before upgrading. Database backups preserve the new records;
optional environments and pretrained weights are separate, reproducible local
installations and are not embedded in workspace backups.

## Optional local ADMET runtime

The base application remains usable without PyTorch, ADMET-AI or Vina. Install
large scientific dependencies in their own environment:

```sh
uv venv data/runtime/discovery --python 3.12
uv pip sync --python data/runtime/discovery/bin/python requirements-discovery.lock
.venv/bin/python -m cvti.discovery_models
```

On Windows, use `data/runtime/discovery/Scripts/python.exe` and configure
`DISCOVERY_PYTHON` accordingly before inspecting the model. The optional lock
records the versions exercised on macOS arm64/Python 3.12; installation on other
platforms needs its own verification. It is separate from the core `uv.lock`.

The inspect command hashes the locally installed checkpoints and writes
`data/models/admet-manifest.json`. It does not train, query an external predictor
or populate compound data. Open **Endpoint predictions → Local model setup &
evidence → Register installed experimental model** to retain the immutable
release in the database. Re-registering the same manifest reuses the release.

The adapter pins **ADMET-AI 2.0.1** and verifies the package version, checkpoint
file set, checkpoint hashes and recorded runtime dependencies before loading
models. It disables DrugBank percentile processing and passes no research
content to an external inference provider. Python network connections are
blocked in the isolated inference process; there is no cloud fallback.

These nine endpoint contracts are deliberately separate from the PCSK9 score:

| Endpoint | Output units / meaning |
|---|---|
| Solubility_AqSolDB | log10(mol/L) |
| Lipophilicity_AstraZeneca | log-ratio, as returned by the pretrained endpoint |
| Caco2_Wang | log10(10^-6 cm/s) |
| Pgp_Broccatelli | Positive-class model output for inhibition, [0,1] |
| CYP3A4_Veith | Positive-class model output for inhibition, [0,1] |
| CYP2D6_Veith | Positive-class model output for inhibition, [0,1] |
| hERG | Positive-class model output for blocking, [0,1] |
| AMES | Positive-class model output for mutagenicity, [0,1] |
| DILI | Positive-class model output for liver-injury label, [0,1] |

Outputs preserve the model's transformations. Negative log-solubility is a
valid logarithmic value; it is not displayed as a negative physical
concentration. Missing/non-finite results, out-of-range classifier outputs and
mismatched molecule identities fail the job. No synthetic fallback fills a
missing endpoint. There is no composite success probability or automatic
clinical interpretation.

### Model reuse and evaluation status

The selected [ADMET-AI release](https://pypi.org/project/admet-ai/2.0.1/) is a
reusable pretrained small-molecule model package. The
[upstream repository](https://github.com/swansonk14/admet_ai) supplies code under
MIT and describes TDC endpoint data; review checkpoint/data terms for the actual
intended distribution. The manifest records this unresolved review rather than
asserting commercial or scientific approval. Species, endpoint task and source
definitions are displayed individually.

Version 2 differs from the original v1 paper/web model. No v1 leaderboard number
is attributed to our installed v2 checkpoint. Training-data overlap with a
submitted compound is unknown, and the application reports no calibrated
confidence or validated applicability domain. A public-aspirin inference run
verifies integration only. Independent evaluation requires an attributable,
compatible dataset and a frozen protocol; prospective performance cannot be
inferred from this smoke test.

## Local docking setup and use

Install the official **AutoDock Vina 1.2.7** executable for your operating system
from [the upstream release](https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.7).
Place it at `data/runtime/vina` (mark executable on macOS/Linux), or set
`VINA_EXECUTABLE` to its path. On Windows this will normally end in `.exe`.
The optional environment above includes **Meeko 0.8.0** for ligand preparation.

1. Prepare and review a rigid receptor PDBQT using an appropriate structure
   workflow. This application does not silently select chains, remove cofactors,
   repair mutations or choose a receptor protonation state.
2. Enter the ligand and upload the prepared receptor. Supply its source,
   preparation notes, target/construct and the pocket's relationship to the assay.
3. Specify a grid center and dimensions (5–40 Å per dimension), seed and search
   exhaustiveness. A grid with no receptor atoms is rejected.
4. Queue the run. Ligand coordinates use ETKDGv3 and MMFF94 when parameterized;
   Meeko prepares the PDBQT. Vina runs locally with one CPU thread.
5. Inspect all returned scores and poses. The viewer includes bounded nearby
   receptor context; download the original PDBQT for full inspection.

Results retain the original receptor, ligand preparation, input settings,
executable hash/version, engine versions, poses and log. The displayed score is
Vina energy in kcal/mol, with RMSD bounds in separate columns. It is not an
experimentally measured affinity. Ligand protonation is not optimized for pH,
and rigid docking omits receptor flexibility and many physical effects.

For PCSK9, choosing an allosteric pocket such as the one represented by 6U26
does not establish the direct PCSK9–LDLR binding endpoint. Receptor/construct,
pocket relevance and reference-ligand redocking require scientific review.

## Assay and SAR workflow

Curve input contains `concentration,response` pairs. Concentrations must be
positive and use explicitly selected molar units. At least six distinct
concentrations and varying responses are required. Zero-dose controls belong
in plate QC, not on the logarithmic fitting axis. Replicates remain separate
rows with equal weights. The fitted midpoint is not automatically IC50/EC50;
that depends on the assay and response definition.

The fit reports residuals, R², range/plateau/parameter warnings and an
approximate midpoint interval only when basic identifiability checks pass.
These intervals assume independent, constant-variance errors. Z-prime uses
sample standard deviations and is undefined when the control means coincide.
Neither calculation approves an assay.

SAR CSV columns:

```text
smiles,value,relation,source_reference,target,endpoint,assay_id,modality,units,data_origin
```

All rows must share target, endpoint, assay, modality, unit and data origin.
The endpoint must be IC50, EC50, Ki or Kd in molar concentration units, relation
must be `=`, and the modality must be `small_molecule`. Repeated standardized
structures require a separately reviewed aggregation; censored values and
mixed contexts are rejected. A pair is flagged at a ≥1 log-unit difference
above the selected fingerprint similarity threshold. Identical fingerprints
are marked and receive no infinite SALI value.

Analog proposals use named SMARTS transformations, preserve their rules and
RDKit version, and return a fingerprint-diversity shortlist. They do not use
an LLM, invent measurements or claim predicted improvement. Evaluate chemical
plausibility and synthesizability before considering any experiment.

## Provenance, recovery and boundaries

- Analysis previews are read-only unless **Save** is selected. Scientific jobs
  necessarily retain their inputs and outputs for reproducibility.
- All saved analyses belong to the selected project. Direct retrieval and retry
  require the same project ID. Model releases are shared local resources.
- Input/result checksums are checked on read; checkpoint and implementation
  checks are enforced before scientific execution. Completed results have no
  edit/delete API. A failed retry creates a new run linked to the old one.
- The worker marks abandoned running jobs interrupted on restart. It never
  silently reruns them. Changed implementation requires a newly submitted job.
- Model errors never become numeric predictions. Source failures never create
  synthetic biological evidence.
- No operation creates curated training measurements, approves an assay or
  grants new authority to the research assistant.
- Saved runs survive browser refresh. Unsaved discovery form/result state is
  session-local; save or download it before refreshing. Existing profile and
  comparison recovery behavior is unchanged.
- Runtime models, test outputs, receptor files and research data stay under
  ignored `data/`, outside Git.

Settings: `DISCOVERY_PYTHON`, `ADMET_MANIFEST`, `VINA_EXECUTABLE`,
`DISCOVERY_TIMEOUT_SECONDS` (default 600, range 10–3600). Run the API and worker
from the same repository root/configuration. Missing executables, modified
weights and timeouts produce actionable failed-run states. Startup only checks
file presence; a completed inference is needed to verify a runtime.

## Interfaces

- `GET /discovery/capabilities`, `/endpoints`, `/models`
- `POST /discovery/models/register-local`
- `POST /discovery/analyze` with `project_id`, `kind`, `payload`, `save`
- `POST /discovery/jobs` with `project_id`, `kind` (`admet` or `docking`), `payload`
- `GET /discovery/runs?project_id=…`
- `GET /discovery/runs/{id}?project_id=…`
- `POST /discovery/runs/{id}/retry?project_id=…`

The API documentation lists field schemas; endpoint analyses have strictly
validated per-kind payloads. API access remains local and unauthenticated,
consistent with the existing solo-workspace architecture.

## Windows verification on this PC — 28 October 2026

The separate environment at `data/runtime/discovery/Scripts/python.exe` was
installed from `requirements-discovery.lock`. It contains ADMET-AI 2.0.1 and
Meeko 0.8.0; the ten installed ADMET checkpoints are pinned in
`data/models/admet-windows-20261028.json`. Official Windows Vina 1.2.7 is at
`data/runtime/vina/vina_1.2.7.exe`. The ignored `.env` now points the API and
worker to these files:

```dotenv
DISCOVERY_PYTHON=./data/runtime/discovery/Scripts/python.exe
ADMET_MANIFEST=./data/models/admet-windows-20261028.json
VINA_EXECUTABLE=./data/runtime/vina/vina_1.2.7.exe
```

Actual local smoke jobs completed in a disposable database: all nine selected
ADMET endpoints for aspirin and three Vina poses for the upstream 1IEP/ABL1
tutorial. ADMET used CPU during this verification; ADMET GPU operation was not
tested. This was not PCSK9 receptor validation or a measured prediction benchmark.
Open Targets PCSK9 and RCSB retrieval also passed with raw responses preserved.

The running user workspace has only the installed experimental ADMET release
metadata registered. No example compounds, assays, observations, predictions or
scientific jobs were added. Checkpoint suitability, training overlap, intended
reuse terms, independent evaluation and calibration remain unresolved.
Logs/manifests are in `data/assistant-training/2026-10-27-evidence-v3/`; connected
runtime and unchanged-table checks are in the subsequent v4 campaign directory.

## Not claimed by this release

No independently validated PCSK9 predictor, clinical success score, qualified
assay approval, synthesis guarantee, calibrated ADMET uncertainty, benchmarked
PCSK9 docking campaign, PBPK, free-energy calculation, protein-binder design,
virtual-cell foundation model or autonomous laboratory/assistant agent is
provided. Those are separate scientific programs with data, evaluation and
compute requirements. The practical connected workflows above are implemented
and tested without weakening those boundaries.
