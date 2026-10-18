# PCSK9 therapeutic intelligence MVP

A lean, Python-first research application for a solo developer. It ingests public PCSK9 records from ChEMBL and Open Targets, stores them in SQLite or PostgreSQL, computes RDKit molecular features, trains an exploratory scikit-learn IC50 classifier, and shows results in Streamlit. It runs on a laptop without a GPU or paid service.

**All predicted scores are research hypotheses, not validated drugs, drug efficacy, clinical advice, or evidence that a compound affects PCSK9 in a patient.** The bundled fixture is wholly synthetic and is only for software testing.

## Architecture

```text
ChEMBL IC50 API ─────┐
                    ├─ ingestion + validation ─ SQLite / PostgreSQL
Open Targets GraphQL ┘                            │
                                                 ├─ RDKit standardization + Morgan fingerprints
                                                 ├─ scaffold-split Random Forest + saved experiment
                                                 └─ FastAPI ─ Streamlit dashboard
```

This is one application package (`src/cvti`), one database, and local model artifacts. Docker Compose can run PostgreSQL alone or the full API and dashboard stack. There are no cloud GPUs, queues, Kubernetes components, or LLM training jobs.

## Roadmap and local operations

See the [approved implementation roadmap](docs/roadmap.md), [verified progress](docs/progress.md), and [startup, diagnostics and recovery guide](docs/operations.md).

## Research workbench

The optional [local pretrained research assistant](docs/pretrained-assistant.md)
summarizes explicitly selected dataset/report excerpts or pasted source text,
with supporting quotes, source hashes and model identity. Open **Research assistant**
to preview evidence; configure a local Ollama model to generate a research draft.
This is a language-model integration, not a new molecular predictor or scientific
approval. Inference is disabled until a local model is configured.

Version 0.2 adds [source/review audits, baseline comparisons, projects, history and durable CSV jobs](docs/research-workflow.md). A [market workflow review](docs/market-workflow-review.md) informed read-only exact, substructure and similarity search over saved collections. Run `cvti doctor` for diagnostics or `cvti start` to launch the API, dashboard and one local worker together.

The [integrated local research workflow](docs/integrated-research-workflow.md) adds
a compound → batch → sample registry, staged CSV registration, sourced assay
protocols/runs/observations with preserved corrections, saved candidate views,
calculated-property filters and explicit model previews. Registry observations
remain unreviewed and do not enter model training. Existing workspaces use an
additive database migration; no registry examples are loaded automatically.

For a guided first session, follow the [step-by-step tutorial](docs/tutorial.md). Start with structure profiles and comparisons without adding data; load the synthetic demonstration only when you choose to.

The Streamlit interface uses a sidebar workspace, molecular structure cards and interactive charts. Open `http://127.0.0.1:8501/` and choose a page:

| Page | What it does |
|---|---|
| Overview | Shows research readiness, saved experiment counts, scaffold evaluation and a preview of stored molecules. |
| Compound registry | Registers sourced compound identities, validates CSV imports before saving, and links material batches and samples. |
| Candidate workbench | Filters registered structures and properties, reruns saved views, inspects raw assay evidence and previews selected model hypotheses. |
| Assay records | Preserves protocol/run/sample context, original values and units, source references and observation corrections. |
| Research assistant | Previews selected evidence and asks an optional local pretrained model for cited, downloadable research drafts. |
| Molecule profile | Draws a supported structure, calculates descriptors, previews an explicitly selected model's score and optionally saves a prediction. |
| Compare molecules | Compares two to six structures, calculated properties and Morgan-fingerprint PCA positions; optionally adds scores from the selected experiment and exports a CSV. |
| Assay review | Filters preserved assay decisions and opens source documents, full descriptions and exclusion reasons. |
| Models & reports | Runs synthetic demonstrations, displays class balance and scaffold holdouts, and exports experiment reports. |
| Datasets & evidence | Inspects version checksums, selection rules, dataset audit and contextual disease evidence. |
| Projects & history | Organizes projects/collections/notes, searches saved structures, retrieves predictions and exports reports. |
| Batch processing | Processes CSV molecule lists using one durable local worker, with per-row outcomes and explicit saving. |

The **Scoring model** selector controls both profile scores and molecule comparisons. Select **Structures only** for calculations without a model. Comparison scores and profile previews do not create prediction records; **Save prediction** does. Invalid submissions clear the previous result. Model and dataset IDs are carried with every returned score. A direct link to the comparison workspace is `http://127.0.0.1:8501/?view=Compare%20molecules`.

Chrome refresh restores the current page, project, scoring model, submitted molecule
inputs and displayed profile/comparison results from a local recovery snapshot.
Keep the `workspace` identifier in the address bar (or bookmark the full URL) to
return to that workspace. A new URL without that identifier starts blank; changing
projects clears the molecule workspace. Text typed into a form is retained after
you submit it. Refresh does not repeat scoring or save predictions. Recovery
snapshots are separate from research records and stay in ignored
`data/workspaces/`; `WORKSPACE_STATE_DIR` can override that location. Only an
opaque identifier appears in the URL, not molecular structures. If local storage
cannot be read or written, the app shows a recovery warning. Saved predictions
remain available in **Projects & history**.

Structure cards report molecular weight, calculated logP and polar surface area; profiles also show hydrogen-bond donors, acceptors and rotatable bonds. These are calculated descriptors, not measured ADMET endpoints or desirability rankings. The interface currently supports the exploratory PCSK9 IC50 classifier; docking, ADMET endpoint models and calibrated uncertainty have not been established. Fingerprint PCA is fitted to the compared molecules only, so its axes and distances change when the comparison set changes. It is a structural visualization, not an applicability-domain validation.

In **Projects & history**, create a collection and add molecules, then search all collections in the selected project or one collection by SMILES. Exact search compares standardized structures; substructure search matches the entered SMILES graph with chirality considered; similarity search ranks Morgan radius-2, 2048-bit fingerprint Tanimoto scores. Results retain collection/entry IDs and notes. The table shows at most 500 hits and **Download search results CSV** exports those displayed hits. A search is read-only and does not create evidence, predictions or measurements. It examines up to 10,000 saved entries per request; select one collection if the scope is larger. Similarity is structural resemblance, not biological activity, calibrated confidence or a validated applicability domain. The API endpoint is `GET /collections/search?project_id=1&smiles=Oc1ccccc1&mode=similarity&min_similarity=0.5`; `mode` can also be `exact` or `substructure`, and optional `collection_id` narrows the scope.

## Quick start: macOS and Linux

Use Python 3.12, the version used for the Phase 1 smoke test. From this repository:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install uv==0.13.1
uv sync --frozen --extra dev
cp .env.example .env
cvti db upgrade
cvti ingest --source fixture
cvti train --source synthetic_fixture
cvti predict 'CC1CCCCC1'
uvicorn cvti.api:app --reload --host 127.0.0.1 --port 8000
```

Alternatively, `cvti start` runs all local components in one foreground terminal. For separate processes, in a second terminal activate the same environment and run:

```bash
streamlit run dashboard.py
```

For CSV jobs started through the dashboard, run `cvti worker` in a third terminal when using separate processes. Open the dashboard URL printed by Streamlit. The API docs are at `http://127.0.0.1:8000/docs`.

## Quick start: Windows PowerShell

Install Python 3.12 first, then run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install uv==0.13.1
uv sync --frozen --extra dev
Copy-Item .env.example .env
cvti db upgrade
cvti ingest --source fixture
cvti train --source synthetic_fixture
cvti predict "CC1CCCCC1"
uvicorn cvti.api:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell window, activate `.venv` and run `streamlit run dashboard.py`. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\cvti.exe` directly. The committed `uv.lock` records exact dependency versions across supported platforms; `uv sync --frozen` installs from that lockfile.

## Docker and PostgreSQL

SQLite is the default and needs no Docker. To use PostgreSQL while running Python on your computer, install Docker. On macOS, [Colima](https://github.com/abiosoft/colima/blob/main/README.md) can provide the local Docker runtime; run `colima start` before the Compose commands and `colima stop` when finished. Start PostgreSQL with:

```bash
docker compose up -d db
```

Set these two values in `.env` (choose a new password before sharing or deploying anything):

```dotenv
POSTGRES_PASSWORD=local_dev_only
DATABASE_URL=postgresql+psycopg://cvti:local_dev_only@127.0.0.1:5432/cvti
```

Run `cvti db upgrade`, then the same `cvti` and server commands. For PostgreSQL, the password in the URL must match `POSTGRES_PASSWORD` (URL-encode special characters in the URL). The database is created by Compose; Alembic applies the versioned schema. Docker's [health-check dependency](https://docs.docker.com/compose/how-tos/startup-order/) keeps the API from starting before PostgreSQL is ready.

To run the complete stack in Docker, stop any locally running API/dashboard on ports 8000/8501, then run:

```bash
docker compose up --build -d
docker compose ps
docker compose exec api cvti ingest --source fixture
docker compose exec api cvti train --source synthetic_fixture
```

Open `http://127.0.0.1:8501` for Streamlit and `http://127.0.0.1:8000/docs` for the API. `docker compose down` stops the stack; its named PostgreSQL and model-artifact volumes retain data. Do not expose the unauthenticated development API to the internet.

If ports 8000/8501 are already in use, set `API_HOST_PORT=18000` and `DASHBOARD_HOST_PORT=18501` in `.env` before starting Compose, then open the corresponding host ports. The containers continue to communicate on their internal ports.

Compose sets the dashboard's browser API reference link to the configured host port. When running a dashboard against another API manually, `API_URL` controls its server connection and the optional `API_REFERENCE_URL` controls the browser documentation link.

## Database migrations

`cvti db upgrade` creates a fresh schema or applies pending Alembic revisions. API startup and other CLI commands call the same upgrade routine. Existing databases made by the first MVP are stamped at the initial revision only when their tables match that baseline, then upgraded without deleting their records. A mismatched schema stops with an error for review. Old experiments receive a `legacy_unverified` dataset version because their original snapshot and review were never stored; this migration cannot reconstruct them. New schema changes should be added as migration files in `migrations/`; do not edit an old revision after it has been used. See the [Alembic migration guide](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).

## Real public data

For the proposed assay review workflow, first save a dated ChEMBL snapshot and generate the review sheet:

```bash
cvti chembl snapshot --output data/pcsk9-chembl-YYYY-MM-DD.json
cvti chembl review-sheet --snapshot data/pcsk9-chembl-YYYY-MM-DD.json --output data/pcsk9-assay-review-YYYY-MM-DD.csv
```

The review sheet is a CSV that can be opened in a spreadsheet app. A qualified reviewer must inspect the full assay descriptions and primary sources. For a suitable direct PCSK9-LDLR binding assay only, set `decision=include`, `endpoint_group=pcsk9_ldlr_binding`, and give a specific `review_note`; leave uncertain assays blank or set `exclude`. Then run:

```bash
cvti chembl curate --snapshot data/pcsk9-chembl-YYYY-MM-DD.json --review data/pcsk9-assay-review-YYYY-MM-DD.csv
cvti datasets list
cvti datasets show 1
```

The curation result prints its actual `dataset_version_id`; substitute that ID for `1` above. A version stores the exact fetched ChEMBL JSON, the review CSV, explicit selection rules and implementation hashes, the selected molecular rows, and SHA-256 checksums in the database. The files can be recovered with `cvti datasets export 1 --kind snapshot --output recovered.json` and the same command with `--kind review`. Re-running identical inputs reuses the version; a changed review or rule implementation creates another. Experiments have a required dataset version link, and training reads that version's stored rows, even if the current measurement table later changes. Choose a historical version with `cvti train --source chembl_curated --dataset-version-id 1`. The default `cvti train --source chembl_curated` selects the newest version and requires status `ready`; pending and empty reviews cannot train. Predictions report the version and whether it has been superseded.

Read the full [assay curation policy](docs/assay-curation.md) before including records. The software enforces basic quality checks and a manual review gate; it does not replace scientific judgment. If the reviewed set is too small for the scaffold split, training stops. The initial `cvti ingest --source live` command remains available for preliminary exploration of ChEMBL and [Open Targets](https://platform-docs.opentargets.org/data-access/graphql-api), but the unreviewed `chembl` source cannot be used to train the baseline. Experiments also record a hash of their training examples, source, sample counts, metrics, and saved model path.

The [14 October 2026 desk review](docs/assay-review-2026-10-14.md) screened all 23 assays in the first saved snapshot and approved none for the narrow direct-binding endpoint. The decision sheet is in `reviews/`; no real-data model has been trained. Original-source verification and independent assay expertise remain necessary before changing an exclusion to inclusion.

The public APIs can be slow or unavailable. `HTTP_MAX_RETRIES`, `HTTP_BACKOFF_SECONDS`, `HTTP_TIMEOUT_SECONDS`, and `CHEMBL_MAX_RECORDS` in `.env` control bounded requests. HTTP 429 and transient 5xx responses are retried with backoff and `Retry-After` when present. Avoid repeatedly querying; for large studies use the providers' bulk downloads.

The built-in fixture is not sourced from either provider. Its source is `synthetic_fixture`; it is kept separate from `chembl` in training and shown as synthetic in the dashboard. Back up `data/cvti.db` before resetting local data: it now contains the only in-database copies of dataset versions and experiment history.

## Dashboard review and exports

Under **Assay review**, choose a stored ChEMBL dataset version to see each assay's source document links, recorded inclusion decision, exclusion reason, activity count, and retained activity count. Filter by decision and choose an assay to read its complete saved description and review note. **Download assay review CSV** exports every assay in the selected version. This view reads preserved inputs; it does not apply today's rules to an older review. An inclusion decision alone does not guarantee that any activities survived the selection rules. New curation runs also record activity exclusion counts per assay; older versions retain their reviewer notes and any metadata exclusions recorded in their review CSV.

Under **Inspect experiment evaluation**, select an experiment and download its **Markdown** or **JSON** report. Each report contains the experiment's own dataset version, source and checksums, stored selection rules, associated assay decisions and source links, evaluation results, and research limitations. Choosing another version in the assay view does not change the experiment export. Synthetic experiments have no ChEMBL assay review; legacy exports explicitly identify missing original provenance. Historic review views are read-only. The revised-review editor holds a draft until explicit submission creates a new version; CSV curation is also available. New inclusions require reviewer/date/primary source and assay comparability fields. See the version 0.2 research workflow guide.

## API and model

- `GET /health`, `GET /summary`
- `POST /fixtures/load`, `GET /measurements`, `GET /evidence`
- `POST /experiments` with `{"source":"synthetic_fixture"}` or `{"source":"chembl_curated"}`; `GET /experiments`
- `GET /dataset-versions`, `GET /dataset-versions/{id}`; `POST /experiments` also accepts `dataset_version_id`
- `GET /dataset-versions/{id}/assays` for recorded assay review details
- `GET /experiments/{id}/report` for JSON, or `?format=markdown` for a downloadable report; exports verify dataset integrity
- `POST /predict` with `{"smiles":"CC1CCCCC1"}`
- `POST /predict` also accepts an explicit `experiment_id` and `save:false` for a preview; saving remains the default
- `POST /molecules/profile` with `{"smiles":"Oc1ccccc1"}` returns a 2D SVG and calculated descriptors
- `POST /molecules/compare` with `{"smiles":["Oc1ccccc1","Cc1ccccc1"],"experiment_id":7}` compares up to six distinct standardized structures without saving predictions; omit the experiment ID for structures only

Molecules are parsed and converted to RDKit charge-parent canonical SMILES. An invalid structure or a molecule with no ring scaffold is rejected. The feature vector is a 2048-bit radius-2 Morgan fingerprint. The illustrative positive class is `pChEMBL IC50 >= 6` (IC50 at or below 1 µM). Duplicate standardized molecules are aggregated by median pChEMBL; contradictory molecules crossing the label threshold are excluded. Five distinct, deterministic holdouts reserve 25% of the scaffold groups and keep Bemis–Murcko scaffolds and identical molecules apart. The fraction of molecules held out can vary with scaffold group sizes. Each split must contain both label classes in train and test; the report gives the number of attempted and rejected partitions. Five valid distinct partitions are required, otherwise training stops. The fixed-seed 150-tree Random Forest is fitted separately on each split. The experiment stores dataset and per-split class counts, balanced accuracy, ROC AUC, average precision, confusion counts, scaffold counts, and zero-overlap checks. It also reports the median and range across splits. After evaluation, a separate prediction model is refit on all molecules in the versioned dataset.

Run `cvti train --source synthetic_fixture` to print the full evaluation report, or choose the saved experiment under **Inspect experiment evaluation** in the dashboard. The older experiments retain their original single-split metrics and are labelled there. See the [scikit-learn validation guide](https://scikit-learn.org/stable/modules/cross_validation.html#group-shuffle-split) for group splitting and the need to reserve unseen data for final evaluation. If model parameters or decision thresholds are tuned in future, use training-only validation and keep an external test set untouched until the final evaluation.

The prediction response shows whether the exact molecule or its scaffold occurred in training. Its number is a model output for prioritizing follow-up experiments, **not a calibrated probability of clinical success**. Training on the fixture demonstrates the software only; its scores have no scientific meaning.

## Scientific limitations

- PCSK9 is a biologically established cholesterol target, but a PCSK9 association score is not proof that a particular molecule treats cardiovascular disease. See the [Open Targets PCSK9 page](https://platform.opentargets.org/target/ENSG00000169174).
- ChEMBL assays differ in constructs, formats, conditions, and source quality. The new manual review gate narrows the intended endpoint, but it does not establish that included assays are comparable; this MVP does not establish selectivity, cell activity, exposure, toxicity, or in vivo efficacy.
- Even repeated scaffold splitting can overestimate prospective performance. The holdouts overlap, and requiring both classes filters the possible partitions; their median and range are descriptive, not independent confidence intervals. The dataset may be small, class imbalanced, biased toward published chemistry, and related across scaffold families.
- Charge-parent standardization can erase relevant salt/protonation information; stereochemistry is retained in canonical SMILES but may be missing from source structures. The current Morgan fingerprints do not encode chirality, so stereoisomers can have identical feature vectors and PCA positions. Acyclic molecules are excluded from this scaffold-split MVP.
- The Random Forest is a baseline, not a medicinal chemistry decision system. No scientific uncertainty calibration, validated applicability domain, external benchmark, temporal performance result, or independent experimental confirmation has been established. The software now supports separate evaluation and source-date checks, but a suitable reviewed external dataset is still unavailable. The current reviewed ChEMBL version approved no measurements, so there is no valid real-data model or later independent dataset to evaluate. A future external or temporal holdout needs another independently reviewed, endpoint-compatible dataset with both classes and enough distinct molecules and scaffolds; overlapping molecules must be excluded before calling it independent.
- Never mix the synthetic fixture with real ChEMBL records when interpreting results. The database separates sources, and training requires a source choice.

## Development milestones

1. **Done here:** locked Python environment, versioned SQLite/PostgreSQL schema, Docker stack, offline fixture-to-dashboard vertical slice, source ingestion, persistence, scaffold-aware baseline, and tests.
2. **Screened conservatively:** proposed direct PCSK9-LDLR binding endpoint, explicit activity/assay gates, raw snapshot and review CSV workflow. The first 23-assay desk review approved no records; independent expert review and original-source verification are still needed.
3. **Dataset versioning done:** database copies and checksums of ChEMBL snapshots, review decisions, selection rules, and selected rows; required experiment links. Next add temporal/external validation, model calibration, and uncertainty analysis.
4. Add authentication and deployment monitoring when remote collaboration or hosting is needed.
5. Seek experimental validation of any candidate hypotheses before making biological or therapeutic claims.

## Tests

```bash
python -m pytest -q
```

Tests use SQLite, synthetic fixtures, and mocked HTTP responses. They do not require Docker, GPUs, or live APIs.
