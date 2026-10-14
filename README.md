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

In a second terminal, activate the same environment and run:

```bash
streamlit run dashboard.py
```

Open the dashboard URL printed by Streamlit. The API docs are at `http://127.0.0.1:8000/docs`.

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

## Database migrations

`cvti db upgrade` creates a fresh schema or applies pending Alembic revisions. API startup and other CLI commands call the same upgrade routine. Existing databases made by the first MVP are stamped at the initial revision only when their tables match that baseline, then upgraded without deleting their records. A mismatched schema stops with an error for review. New schema changes should be added as migration files in `migrations/`; do not edit an old revision after it has been used. See the [Alembic migration guide](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).

## Real public data

For the proposed assay review workflow, first save a dated ChEMBL snapshot and generate the review sheet:

```bash
cvti chembl snapshot --output data/pcsk9-chembl-YYYY-MM-DD.json
cvti chembl review-sheet --snapshot data/pcsk9-chembl-YYYY-MM-DD.json --output data/pcsk9-assay-review-YYYY-MM-DD.csv
```

The review sheet is a CSV that can be opened in a spreadsheet app. A qualified reviewer must inspect the full assay descriptions and primary sources. For a suitable direct PCSK9-LDLR binding assay only, set `decision=include`, `endpoint_group=pcsk9_ldlr_binding`, and give a specific `review_note`; leave uncertain assays blank or set `exclude`. Then run:

```bash
cvti chembl curate --snapshot data/pcsk9-chembl-YYYY-MM-DD.json --review data/pcsk9-assay-review-YYYY-MM-DD.csv
cvti train --source chembl_curated
```

Read the full [assay curation policy](docs/assay-curation.md) before including records. The software enforces basic quality checks and a manual review gate; it does not replace scientific judgment. If the reviewed set is too small for the scaffold split, training stops. The initial `cvti ingest --source live` command remains available for preliminary exploration of ChEMBL and [Open Targets](https://platform-docs.opentargets.org/data-access/graphql-api), but the unreviewed `chembl` source cannot be used to train the baseline. Experiments record a hash of their training rows, source, sample counts, metrics, and saved model path.

The [14 October 2026 desk review](docs/assay-review-2026-10-14.md) screened all 23 assays in the first saved snapshot and approved none for the narrow direct-binding endpoint. The decision sheet is in `reviews/`; no real-data model has been trained. Original-source verification and independent assay expertise remain necessary before changing an exclusion to inclusion.

The public APIs can be slow or unavailable. `HTTP_MAX_RETRIES`, `HTTP_BACKOFF_SECONDS`, `HTTP_TIMEOUT_SECONDS`, and `CHEMBL_MAX_RECORDS` in `.env` control bounded requests. HTTP 429 and transient 5xx responses are retried with backoff and `Retry-After` when present. Avoid repeatedly querying; for large studies use the providers' bulk downloads.

The built-in fixture is not sourced from either provider. Its source is `synthetic_fixture`; it is kept separate from `chembl` in training and shown as synthetic in the dashboard. Remove the local `data/` directory to reset SQLite data and model artifacts.

## API and model

- `GET /health`, `GET /summary`
- `POST /fixtures/load`, `GET /measurements`, `GET /evidence`
- `POST /experiments` with `{"source":"synthetic_fixture"}` or `{"source":"chembl_curated"}`; `GET /experiments`
- `POST /predict` with `{"smiles":"CC1CCCCC1"}`

Molecules are parsed and converted to RDKit charge-parent canonical SMILES. An invalid structure or a molecule with no ring scaffold is rejected. The feature vector is a 2048-bit radius-2 Morgan fingerprint. The illustrative positive class is `pChEMBL IC50 >= 6` (IC50 at or below 1 µM). Duplicate standardized molecules are aggregated by median pChEMBL; contradictory molecules crossing the label threshold are excluded. A deterministic group split keeps Bemis–Murcko scaffolds, and therefore identical molecules, apart between training and test. The classifier is a fixed-seed 150-tree Random Forest. The saved experiment includes balanced accuracy, ROC AUC, train/test counts, and explicit zero-overlap checks.

The prediction response shows whether the exact molecule or its scaffold occurred in training. Its number is a model output for prioritizing follow-up experiments, **not a calibrated probability of clinical success**. Training on the fixture demonstrates the software only; its scores have no scientific meaning.

## Scientific limitations

- PCSK9 is a biologically established cholesterol target, but a PCSK9 association score is not proof that a particular molecule treats cardiovascular disease. See the [Open Targets PCSK9 page](https://platform.opentargets.org/target/ENSG00000169174).
- ChEMBL assays differ in constructs, formats, conditions, and source quality. The new manual review gate narrows the intended endpoint, but it does not establish that included assays are comparable; this MVP does not establish selectivity, cell activity, exposure, toxicity, or in vivo efficacy.
- Even scaffold splitting can overestimate prospective performance. The dataset may be small, class imbalanced, biased toward published chemistry, and related across scaffold families. One holdout split is not a confidence interval.
- Charge-parent standardization can erase relevant salt/protonation information; stereochemistry is retained but may be missing from source structures. Acyclic molecules are excluded from this scaffold-split MVP.
- The Random Forest is a baseline, not a medicinal chemistry decision system. No uncertainty calibration, applicability-domain validation, external benchmark, temporal split, or independent experimental confirmation is included.
- Never mix the synthetic fixture with real ChEMBL records when interpreting results. The database separates sources, and training requires a source choice.

## Development milestones

1. **Done here:** locked Python environment, versioned SQLite/PostgreSQL schema, Docker stack, offline fixture-to-dashboard vertical slice, source ingestion, persistence, scaffold-aware baseline, and tests.
2. **Screened conservatively:** proposed direct PCSK9-LDLR binding endpoint, explicit activity/assay gates, raw snapshot and review CSV workflow. The first 23-assay desk review approved no records; independent expert review and original-source verification are still needed.
3. Add dataset versioning in the database, temporal/external validation, model calibration, and uncertainty analysis.
4. Add authentication and deployment monitoring when remote collaboration or hosting is needed.
5. Seek experimental validation of any candidate hypotheses before making biological or therapeutic claims.

## Tests

```bash
python -m pytest -q
```

Tests use SQLite, synthetic fixtures, and mocked HTTP responses. They do not require Docker, GPUs, or live APIs.
