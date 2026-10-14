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

This is one application package (`src/cvti`), one database, and local model artifacts. `compose.yaml` runs only PostgreSQL. There are no cloud GPUs, queues, Kubernetes components, or LLM training jobs.

## Quick start: macOS and Linux

Use Python 3.11, 3.12, or 3.13. From this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
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

Install Python 3.11–3.13 first, then run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
cvti ingest --source fixture
cvti train --source synthetic_fixture
cvti predict "CC1CCCCC1"
uvicorn cvti.api:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell window, activate `.venv` and run `streamlit run dashboard.py`. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\cvti.exe` directly.

## Optional PostgreSQL

SQLite is the default. To use PostgreSQL, install Docker, then:

```bash
docker compose up -d db
```

Set these two values in `.env` (choose a new password before sharing or deploying anything):

```dotenv
POSTGRES_PASSWORD=local_dev_only
DATABASE_URL=postgresql+psycopg://cvti:local_dev_only@127.0.0.1:5432/cvti
```

Then run the same `cvti` and server commands. For PostgreSQL, the password in the URL must match `POSTGRES_PASSWORD`. The database is created by Compose; application tables are created automatically at startup. This MVP has no schema migrations yet. Do not expose the unauthenticated development API to the internet.

## Real public data

With an internet connection:

```bash
cvti ingest --source live
cvti train --source chembl
```

Live ingestion queries [ChEMBL's REST API](https://www.ebi.ac.uk/chembl/api/data/docs) for human PCSK9 target `CHEMBL2929`, IC50 measurements with `=` relation, nM units, and a pChEMBL value. It queries the [Open Targets GraphQL API](https://platform-docs.opentargets.org/data-access/graphql-api) for PCSK9 `ENSG00000169174` and its top 20 associated diseases. Data source IDs, timestamps, assay IDs, canonical structures, and links are stored. Re-running ingestion skips previously stored ChEMBL activity IDs, preserving the collected measurement snapshot. Experiments record a hash of the exact curated training rows, source, sample counts, metrics, and saved model path.

The public APIs can be slow or unavailable. `HTTP_MAX_RETRIES`, `HTTP_BACKOFF_SECONDS`, `HTTP_TIMEOUT_SECONDS`, and `CHEMBL_MAX_RECORDS` in `.env` control bounded requests. HTTP 429 and transient 5xx responses are retried with backoff and `Retry-After` when present. Completed ChEMBL pages stay saved if a later request fails. Avoid repeatedly scraping; for large studies use the providers' bulk downloads.

The built-in fixture is not sourced from either provider. Its source is `synthetic_fixture`; it is kept separate from `chembl` in training and shown as synthetic in the dashboard. Remove the local `data/` directory to reset SQLite data and model artifacts.

## API and model

- `GET /health`, `GET /summary`
- `POST /fixtures/load`, `GET /measurements`, `GET /evidence`
- `POST /experiments` with `{"source":"synthetic_fixture"}` or `{"source":"chembl"}`; `GET /experiments`
- `POST /predict` with `{"smiles":"CC1CCCCC1"}`

Molecules are parsed and converted to RDKit charge-parent canonical SMILES. An invalid structure or a molecule with no ring scaffold is rejected. The feature vector is a 2048-bit radius-2 Morgan fingerprint. The illustrative positive class is `pChEMBL IC50 >= 6` (IC50 at or below 1 µM). Duplicate standardized molecules are aggregated by median pChEMBL; contradictory molecules crossing the label threshold are excluded. A deterministic group split keeps Bemis–Murcko scaffolds, and therefore identical molecules, apart between training and test. The classifier is a fixed-seed 150-tree Random Forest. The saved experiment includes balanced accuracy, ROC AUC, train/test counts, and explicit zero-overlap checks.

The prediction response shows whether the exact molecule or its scaffold occurred in training. Its number is a model output for prioritizing follow-up experiments, **not a calibrated probability of clinical success**. Training on the fixture demonstrates the software only; its scores have no scientific meaning.

## Scientific limitations

- PCSK9 is a biologically established cholesterol target, but a PCSK9 association score is not proof that a particular molecule treats cardiovascular disease. See the [Open Targets PCSK9 page](https://platform.opentargets.org/target/ENSG00000169174).
- ChEMBL assays differ in constructs, formats, conditions, and source quality. The current IC50 filter and validity checks are basic; this MVP does not establish comparable mechanisms, selectivity, cell activity, exposure, toxicity, or in vivo efficacy.
- Even scaffold splitting can overestimate prospective performance. The dataset may be small, class imbalanced, biased toward published chemistry, and related across scaffold families. One holdout split is not a confidence interval.
- Charge-parent standardization can erase relevant salt/protonation information; stereochemistry is retained but may be missing from source structures. Acyclic molecules are excluded from this scaffold-split MVP.
- The Random Forest is a baseline, not a medicinal chemistry decision system. No uncertainty calibration, applicability-domain validation, external benchmark, temporal split, or independent experimental confirmation is included.
- Never mix the synthetic fixture with real ChEMBL records when interpreting results. The database separates sources, and training requires a source choice.

## Development milestones

1. **Done here:** offline fixture-to-dashboard vertical slice, source ingestion, persistence, scaffold-aware baseline, and tests.
2. Review assay-level ChEMBL curation with a domain expert; define a consistent endpoint and minimum data quality rules.
3. Add frozen public-data snapshots, dataset versioning, temporal/external validation, model calibration, and uncertainty analysis.
4. Add migration tooling, authentication, and deployment monitoring only when remote collaboration or hosting is needed.
5. Seek experimental validation of any candidate hypotheses before making biological or therapeutic claims.

## Tests

```bash
python -m pytest -q
```

Tests use SQLite, synthetic fixtures, and mocked HTTP responses. They do not require Docker, GPUs, or live APIs.
