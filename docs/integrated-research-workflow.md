# Integrated local research workflow

Added 18 October 2026 on `codex/integrated-research-workflows`. This release
connects compound identity, material, recorded assays and candidate inspection.
It keeps the existing curated-data and model evaluation workflow separate.

## What informed the design

| Public reference | Pattern applied here | Implementation boundary |
|---|---|---|
| [CDD registration forms](https://support.collaborativedrug.com/hc/en-us/articles/45839528903828-Configuring-Registration-Forms-and-Systems) and [validation](https://support.collaborativedrug.com/hc/en-us/articles/214359643-Molecule-Validation-Rules-during-Registration) | Compound → batch → sample identity, column mapping and a validation stage before registration. | A local registry, not a complete inventory or procurement system. No quantities or automated laboratory operations. |
| [Benchling schemas](https://docs.benchling.com/docs/schemas) | Explicit protocol, run, sample and observation links with source context. | PCSK9 records only; recording is not assay approval or authentication of the operator's identity. |
| [LiveDesign release notes](https://www.schrodinger.com/life-science/download/release-notes/) | A candidate table, calculated-property plots, saved filters and explicitly selected model previews. | Existing local models only. No inference of clinical usefulness, new docking engine or molecular generation. |
| [AMPL](https://github.com/ATOMScience-org/AMPL) and [Chemprop](https://github.com/chemprop/chemprop) | Preserve model/dataset identity, immutable evaluation context and errors alongside predictions. | Existing frozen-protocol Dummy/LR/RF implementations remain the supported engines. No new molecular checkpoint is introduced. |
| [OpenADMET policies](https://openadmet.org/policies/) | Make limitations and evidence gaps visible; keep independent evaluation separate. | No new real-data performance or calibration claim. |

This is an implementation of selected workflow patterns, not equivalent product
coverage or scientific readiness. Existing RDKit and locked dependencies are
reused. No external repository code or model weights were imported.

## Start and upgrade

Back up an existing research workspace first, following [operations](operations.md).
Stop the API, dashboard and worker before upgrading an older workspace. Run:

```bash
cvti db upgrade
cvti start
```

The additive `e40c6d53a934` migration creates registry tables. Existing
collections, measurements, dataset versions, evaluations and predictions retain
their identities and contents. Startup also performs supported schema upgrades
under the application's maintenance lock. The migration does not populate the
new registry from collections or load demonstration data.

## 1. Register compound identities

Open **Compound registry** in the selected project. Enter a SMILES, choose its
modality explicitly, and supply an attributable source reference. Names and notes
are optional. Forms start blank.

Registration records the original SMILES, charge-parent canonical SMILES,
structure SHA-256, chemistry policy, RDKit version, formula and calculated
descriptors. Multiple fragments and detected unassigned tetrahedral stereocenters
produce warnings. A matching standardized structure in the same project returns
the existing ID without overwriting its name, notes or source. Conflicting
modality labels are rejected. Distinct specified stereoisomers remain separate.

Registration supports valid acyclic structures with at least two heavy atoms.
The training and prediction workflows still require their existing supported
ring scaffolds. Registering a compound does not make it a supported model input.

To transfer an existing collection, download its CSV in **Projects & history**,
then explicitly import it using the workflow below and select the modality.

## 2. Preview and submit a CSV

In **CSV registration**, upload a UTF-8 CSV and select the SMILES column, optional
name/notes columns, modality and source reference. Files may contain at most
1,000 data rows. Different modalities require separate imports.

**Preview registration** retains the exact decoded UTF-8 input (including BOM and
line endings), its SHA-256, the mapping and chemistry versions, and the checksummed
plan. Each row is labelled ready, existing, duplicate or error. This creates an
import draft but registers no compounds or material.

Inspect the table, then choose **Register valid rows from this preview**. Only
ready and existing rows are processed. Duplicate/error rows remain in the draft
for inspection. Registration is atomic; a conflict rolls back the whole submission.
Submitting a committed preview again returns its recorded outcome without adding
duplicates. A changed plan, input or chemistry version requires a new preview.
Preview history remains available after a browser restart.

Imports create compound identities only. Record physical batches and samples
explicitly when their material and source are known.

## 3. Record material and assay context

Use **Batches & samples** to link a batch to its compound and a sample to its batch.
Each batch needs a source reference and an explicit `research` or `synthetic`
origin. Sample location and notes are optional.

In **Assay records**, create a protocol with its endpoint, readout type, units,
modality, species, constructs, method, conditions and original source. PCSK9–LDLR
binding, expression and secretion are separate endpoints. Different assay formats,
units or conditions require separate protocol records.

Record a run under the protocol with its actual experiment date, operator, origin
and source. Choose a compatible sample and record a source result identifier,
numeric value, equality/inequality relation and source reference. Values must be
finite; units must exactly match the protocol, and no conversion or averaging is
performed. Compound and protocol modalities must match. Synthetic material can
only be linked to synthetic runs.

Observations retain the original numeric text as well as a numeric display value.
For a transcription correction, select the previous observation, use a new source
result ID, and explain the correction in the notes. The correction must refer to
the same run and sample. The original remains visible with `is_current=false`;
correction chains and their sources remain intact. Protocols and runs are append-only:
record a new protocol/run with source-linked notes when their meaning changes.

All observations remain `recorded_unreviewed`. They never become `Measurement`
rows or `DatasetVersion` training records through this interface. Qualified source
review, comparability assessment and the existing dataset/evaluation gates still
apply before scientific training.

## 4. Inspect candidates and model hypotheses

Open **Candidate workbench** to filter registered compounds by name/notes,
modality, molecular weight, calculated logP, exact structure, substructure or
Morgan radius-2, 2048-bit Tanimoto similarity. Save the applied criteria under a
name. A saved view retains its schema and checksum, not a frozen result list;
rerunning it searches the current project registry.

The candidate table and property plot describe structures only. The evidence
panel shows individual sourced observations without pooling endpoints, units,
replicates or origins. CSV download exports the displayed candidates. Searches
examine projects of up to 10,000 compounds; the default table limit is 500.

Select a model in the sidebar, choose up to 50 candidates, and explicitly preview
scores. The output identifies the experiment, immutable dataset and model card.
Each candidate has an outcome, including unsupported inputs or missing artifacts.
This page scores small-molecule hypotheses only; no peptide predictor has been
evaluated. Previews save no predictions or other research records. Score results
and their provenance can be downloaded as JSON. Switching projects clears temporary
candidate/import output; saved views and import drafts remain in their own project.

## 5. Export and recover

**Prepare registry and assay export** produces a ZIP for the selected project:
compounds, batches, samples, protocols, runs, raw observations and correction
history, saved view criteria, original import CSVs, validation plans and outcomes.
The export reads a consistent database snapshot so concurrent additions do not
produce missing compound/material links in the package. The manifest records
SHA-256 values for every included file. JSON retains exact
numeric text. CSV exports escape spreadsheet formula prefixes. The package is a
portable research record, not a model release or proof of assay correctness.

The normal backup/restore system includes these tables and preserves registry
and import identities. Back up before upgrades and restore into a new destination.

## API reference

All routes below are under `/registry`; see local FastAPI `/docs` for full schemas.

| Operation | Routes |
|---|---|
| Compound identity | `GET/POST /compounds`, `GET /compounds/{id}?project_id=...` |
| Material | `GET /materials`, `POST /batches`, `POST /samples` |
| Assay records | `GET/POST /protocols`, `GET/POST /runs`, `GET/POST /observations` |
| Staged CSV registration | `POST /imports/preview`, `GET /imports`, `GET /imports/{id}`, `POST /imports/{id}/commit` |
| Candidate inspection | `POST /workbench/search`, `POST /workbench/score` |
| Saved criteria | `GET/POST /views`, `POST /views/{id}/run` |
| Project research export | `GET /export?project_id=...` |

Mutation bodies carry `project_id`. Commit requires the preview's `plan_sha256`.
Search, saved-view execution and scoring are read-only POST operations. Nested
material/run links and all scoring inputs must belong to the selected project.
These are local scope checks; this release does not implement multi-user access
control or remote hosting.
