# Research workflow additions in 0.2

The application remains a local research tool. The owner has no qualified assay reviewer yet and has selected no-cost local operation for this release. Real-data training and hosted/commercial stages remain gated. The [progress tracker](progress.md) distinguishes implemented software from scientific acceptance.

## Source snapshots

```bash
cvti chembl snapshot --output data/pcsk9-new-snapshot.json
cvti evidence-snapshot --output data/opentargets-context.json
```

New ChEMBL snapshots use schema 2, preserving response bodies as base64 plus their SHA-256, retrieval start/end times, query/cap, per-resource pagination and observed live release at start/end. A consistent observed live release is not a pinned bulk release. Capped, interrupted, inconsistent or unknown-completion snapshots cannot be newly curated. An interrupted request retains the partial file and exits with an actionable error; retry to a NEW filename. Older schema-1 files remain readable with completeness/release explicitly unknown.

Open Targets context is a separate immutable file. The initial evidence query takes 20 associations and is labelled a bounded sample, not a complete extract or training dataset.

### Named bulk extracts

Prepare a target-specific JSON extract from a named official bulk distribution with `activities` and `assays` arrays. Activity fields follow the existing ChEMBL quality policy: activity/molecule/assay/target IDs, human target organism, standardized exact IC50 in nM, pChEMBL, original structure/value, quality flags and source document IDs. Assay rows need target relationship, confidence, type and full description. Preserve publication dates if available, without substituting retrieval dates.

```bash
cvti chembl import-extract --input /path/to/target-extract.json --release ChEMBL_RELEASE_ID --output data/named-extract.json
```

The wrapper preserves exact original bytes/checksum and supplied release attribution. It does not independently certify that you extracted the claimed official release. Current importer accepts this JSON interchange format, not an entire multi-gigabyte ChEMBL database. Other targets are rejected.

## Reviews and audits

```bash
cvti chembl review-sheet --snapshot data/named-extract.json --output data/review.csv
# Complete a qualified original-source review before marking any assay include.
cvti chembl curate --snapshot data/named-extract.json --review data/review.csv
cvti datasets audit DATASET_ID
```

New inclusions require `review_note`, the matching endpoint, `reviewer`, `reviewed_at` (ISO date/time), `primary_source`, `species`, `protein_constructs`, `measurement_method` and `experimental_conditions`. Unknown fields must not be invented. This records a person's assertions, not independent credential verification. Old preserved review bytes and hashes are never rewritten.

**Assay review → Draft a revised review** opens an editable CSV representation. Downloading or editing a draft does not change the database. **Submit revised review** explicitly curates a new version. Pending or empty reviews cannot train. Invalid submissions leave the prior version intact.

**Datasets & evidence → Dataset audit and training feasibility** shows duplicates, conflicting threshold labels, unspecified stereochemistry, identical Morgan fingerprints, class/scaffold counts, repeated document IDs and the software's ability to obtain five splits. Export its JSON before training. Passing the minimum checks is not scientific approval.

## Frozen development protocols and baselines

```bash
cvti protocol --dataset-version-id DATASET_ID
cvti train --source chembl_curated --dataset-version-id DATASET_ID --protocol-id PROTOCOL_ID --model-kind dummy
cvti train --source chembl_curated --dataset-version-id DATASET_ID --protocol-id PROTOCOL_ID --model-kind logistic_regression
cvti train --source chembl_curated --dataset-version-id DATASET_ID --protocol-id PROTOCOL_ID --model-kind random_forest
```

These real-data commands require a ready reviewed version. Use `--source synthetic_fixture` only for demonstration versions. Without a protocol ID, training freezes/reuses a protocol before any fit. The protocol stores exact train/test assignments, feature hash/settings, thresholds, seed and source-overlap disclosures. Identical fingerprint representations cannot cross a development partition. Protocol reuse checks its checksum, dataset and feature implementation.

The Models & reports page can run the three fixed baselines on one chosen dataset and show their development results. Compare results only when both dataset and protocol match. A dummy baseline and class prevalence provide context for model performance. No automatic parameter tuning or promotion occurs. Per-split reports include predictions, confusion counts, prevalence, Brier/log loss and reliability bins. These are raw, uncalibrated score diagnostics; no calibrated scientific model has been established.

A separate real final test set is not currently available or reserved. Development holdouts overlap and are not independent confidence intervals. If future tuning is introduced, final data must first be designated outside that process.

## Evaluate an existing model

```bash
cvti evaluate --experiment-id EXPERIMENT_ID --dataset-version-id SEPARATE_DATASET_ID
cvti evaluate --experiment-id EXPERIMENT_ID --dataset-version-id SEPARATE_DATASET_ID --mode later
```

Evaluation does not refit the model. The target, endpoint and source type must match. Seen molecules/fingerprints are removed; shared source publications are rejected; both classes must remain. Original ISO publication dates for every activity are needed for `later` mode. Unknown source independence is labelled unknown; a synthetic evaluation never establishes biological independence. Repeated evaluations against a dataset are counted and disclosed. Reports/model cards include evaluation records, rather than assuming any such evaluation demonstrates generalization.

Model cards label fixture models synthetic demonstrations and real models experimental. A high score does not automatically assign research-evaluated status. Nearest training compounds use Tanimoto similarity with measurement/assay/document references when preserved. Similarity is context, not a validated applicability threshold or proof of activity.

## Projects and prediction history

Select **Research project** in the sidebar. Existing experiments and predictions were migrated into **Local project**. **Projects & history** supports project names/notes, named molecule collections, molecule notes, paginated prediction history and CSV export. Duplicate standardized molecules in a collection are rejected. Preview scores and structure comparisons do not save predictions.

Choose an experiment in the history filter, select saved prediction IDs and prepare a **unified research report ZIP**. It contains the selected experiment/report, dataset audit, assay review, model card, project context, selected predictions and file checksums. It never substitutes the newest experiment for your selection. This is local project organization, NOT multi-user authorization.

## Durable CSV processing

Start with `cvti start` (includes a worker) or start `cvti worker` alongside manually launched servers. In **Batch processing**:

1. Upload a UTF-8 CSV and select its SMILES column.
2. Choose Structures only or an explicit model in the sidebar.
3. Optionally enable saving predictions (requires a model).
4. Submit the job; refresh to inspect progress.
5. Download CSV results with row-level success, duplicate and error outcomes.

Default maximum: 1,000 rows (`BATCH_MAX_ROWS` is configurable). A duplicate canonical structure is reported without a duplicate prediction. Results and predictions commit together after each row. Restarting the worker marks unfinished work interrupted; retry explicitly to continue remaining rows. Jobs persist when the browser closes. One local worker is supported; this is not a distributed job system.

## Additive API interfaces

- `GET /dataset-versions/{id}/audit`
- `GET /dataset-versions/{id}/review-sheet` → JSON containing `csv_content`
- `POST /dataset-versions/{id}/reviews` with `csv_content` → explicitly curate a new version
- `POST /experiments` adds optional `model_kind`, `protocol_id`, `project_id`
- `GET /experiments/{id}/model-card`
- `GET/POST /projects`; `PATCH /projects/{id}`
- `GET/POST /collections`; `GET/POST /collections/{id}/molecules`
- `GET /predictions?project_id=1&experiment_id=ID&offset=0&limit=100&format=json|csv`
- `POST /batch-jobs` with `csv_content`, `smiles_column`, optional `experiment_id`, `project_id`, `save_predictions`
- `GET /batch-jobs?project_id=1`; `GET /batch-jobs/{id}?format=json|csv`; `POST /batch-jobs/{id}/retry`
- `GET /research-reports/{experiment_id}?project_id=1&prediction_ids=ID` → ZIP

Existing local endpoints remain available. New historical metadata is additive; unknown legacy provenance stays unknown. Host only on your local machine until the roadmap's authentication/authorization and deployment gates are implemented.
