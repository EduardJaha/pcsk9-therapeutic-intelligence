# PCSK9 assay curation, version 1

This is a **proposed research selection policy**, not a validated PCSK9 activity dataset. A domain expert must inspect the assay descriptions and original studies before any real records are approved. ChEMBL target assignment and assay type alone do not establish a common biological readout.

## Endpoint being selected

The only review group supported here is `pcsk9_ldlr_binding`: a concentration-response IC50 for inhibition of the **direct interaction between PCSK9 and LDL receptor (LDLR)**. For version 1, the binding partner should be LDLR or its extracellular domain; isolated EGF-A/AB fragments require a separate endpoint review. An assay measuring cellular PCSK9 expression, secretion, translation, transcription, LDL uptake, degradation, or an unspecified "PCSK9 inhibition" readout belongs outside this group, even if ChEMBL labels it as binding (`B`). A reviewer should record why an original experimental source and the assay description support a direct PCSK9-LDLR binding readout, including construct/species and detection method when available. If the readout or source is unclear, leave it unapproved.

Different direct binding technologies and constructs may still be noncomparable. The current group is a starting point for review, not proof that pooled IC50 values are scientifically exchangeable. Split into narrower groups before modeling if the reviewed assays differ materially.

## Automatic gates

An activity must have the human PCSK9 target `CHEMBL2929`, standardized IC50 in nM with an exact `=` relation, a positive standard value consistent with pChEMBL within 0.1 log units, pChEMBL between 3 and 12, no flagged duplicate, no validity concern except `Manually validated`, a compound/assay/activity ID, and an RDKit-readable molecule with a ring scaffold. Its assay must be directly assigned to PCSK9 (`relationship_type=D`, `confidence_score=9`), classified `B`, and have a description. These checks exclude many uncertain rows but **do not identify the assay mechanism**.

ChEMBL documents [assay types, confidence scores, pChEMBL, data validity, and duplicate flags](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/chembl-data-questions), and explains the [target relationship code](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/target-questions). The [web service guide](https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services) describes the activity and assay resources.

## Review and import

Run these commands from the project folder with the Python environment active:

```bash
cvti chembl snapshot --output data/pcsk9-chembl-YYYY-MM-DD.json
cvti chembl review-sheet --snapshot data/pcsk9-chembl-YYYY-MM-DD.json --output data/pcsk9-assay-review-YYYY-MM-DD.csv
```

The raw snapshot is bounded by `CHEMBL_MAX_RECORDS`, dated, and never overwritten. The CSV has one row per assay appearing in that snapshot, with an assay link and source document IDs when available. `machine_issue` shows automatic assay exclusions. Read each candidate's full description and primary source. Set `decision` to `include` only for a direct PCSK9-LDLR binding assay, set `endpoint_group` to `pcsk9_ldlr_binding`, and write a specific `review_note`. Use `exclude` or leave blank when uncertain.

Then run:

```bash
cvti chembl curate --snapshot data/pcsk9-chembl-YYYY-MM-DD.json --review data/pcsk9-assay-review-YYYY-MM-DD.csv
cvti datasets list
```

The curation command reports counts for every exclusion reason and a database `dataset_version_id`. It stores the exact snapshot bytes, review CSV bytes, selection rules and implementation hashes, and selected rows with SHA-256 checksums. You can inspect a version with `cvti datasets show ID` and recover files with `cvti datasets export ID --kind snapshot --output recovered.json` or `--kind review --output recovered.csv`. Keep external backups of the database and source files too; `data/` is intentionally excluded from Git.

An undecided assay that passes the automatic gates gives the version status `pending_review`; the current `chembl_curated` table is not changed. A completed review with zero approved activities gives `reviewed_empty` and clears the current curated table. A completed review with approved activities gives `ready` and replaces the current curated table. Earlier versions remain stored. Only a `ready` version can train: `cvti train --source chembl_curated --dataset-version-id ID`. Without an ID, training uses the newest version. If too few distinct molecules or scaffolds survive, training stops instead of weakening the quality rules. Each experiment records the version it used, so the original training rows and decisions can be inspected later.

The snapshot captures a particular API response and retrieval time, not an independently verified ChEMBL release identifier. Because a paginated live API pull could span an update, preserve the raw response and its checksum; for formal release-level reproducibility, use a named ChEMBL bulk release and record its release identifier separately.

The older `cvti ingest --source live` path stores a broad, preliminary ChEMBL collection as `chembl` for exploration. Training from that unreviewed source is disabled. The synthetic fixture is separate and remains useful for software smoke tests only.

## Review questions for a domain expert

1. Does the original assay measure the PCSK9-LDLR interaction directly, or a downstream cellular effect?
2. Are target species, constructs, detection methods, incubation time, and controls sufficiently described?
3. Are IC50 values comparable across the assays being pooled, or should they form separate endpoint groups?
4. Are there possible assay artifacts, interfering compounds, duplicated publications, or stereochemical ambiguities?
5. Does the final set have enough independent molecules and scaffold diversity for a meaningful holdout evaluation?

Any resulting model score remains an exploratory research hypothesis. It does not establish biological activity in patients or therapeutic value.
