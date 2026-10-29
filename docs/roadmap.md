# PCSK9 Lab implementation roadmap

Approved direction: reliable solo tool → private team workspace → commercial research service. Prioritize supported cardiovascular target models before separate ADMET/docking projects. This file preserves task IDs from the approved roadmap. See [progress](progress.md) for actual evidence and gates; a feature existing in code does not imply scientific validation.

## Working rules

Preserve records through migrations. Keep the Python modular monolith, FastAPI, Streamlit, SQLite locally and PostgreSQL for collaboration. No required GPU purchase, Kubernetes or foundation-model training. The user authorized optional local pretrained inference on 17 October 2026; see [the assistant guide](pretrained-assistant.md). No paid infrastructure, deletion, user outreach, billing activation or external deployment without the required explicit instruction/selection. Use synthetic/mocked data in normal tests. A real-data approval needs appropriate assay expertise. Synthetic, experimental and research-evaluated models must be distinguishable. Changes to chemistry and endpoint policies create new versions; historic manifests remain unchanged.

For each task: document the interface, test meaningful success/failure cases, preserve backwards compatibility, record the verification and remaining requirements. States: **Not started**, **In progress**, **Waiting on dependency**, **Verified complete**. Record software, scientific-data, model-evidence, usability and commercial readiness separately. The earlier 55% estimate described only the narrower research MVP.

## A — Dependable local application

### R1 — Automated testing on GitHub

Python 3.12/locked dependencies; push and PR checks; offline SQLite suite plus separate PostgreSQL integration; fresh creation and preserving upgrades from supported old schemas. No required live API calls. **Acceptance:** GitHub checks pass for both backends through fixture → training → prediction. No dependencies.

### R2 — Backup and restore

CLI create/inspect/verify/restore archives containing DB, referenced models and retained inputs; checksums, schema/app version. SQLite then PostgreSQL client utilities. Require stopped writers. Restore to new destinations by default; explicit replacement only; relocate model paths. **Acceptance:** restore elsewhere reproduces manifests/reports/predictions. Depends R1.

### R3 — Experiment provenance and artifact integrity

Record Git revision/dirty state, Python/library versions, exact model/fingerprint/threshold/seed settings and train/test assignments. Atomic model writes, pre-deserialization SHA-256 checks; failures leave no successful-looking experiment. Preserve legacy unknowns. **Acceptance:** report identifies exact inputs/settings/environment/artifact; changed artifact never loads. Depends R1.

### R4 — Startup diagnostics

`cvti doctor`: read-only configuration, DB/schema, models and server checks; occupied-port diagnosis; Windows/macOS/Linux helpers and stop instructions. **Acceptance:** routine startup failures have actionable messages. Depends R1.

### R5 — Dependable local release

Offline SQLite/PostgreSQL workflow, empty/populated dashboard, restore exercise, fresh-checkout instructions and documented release tag. **Acceptance:** fresh and restored workspaces pass. Depends R1–R4.

## B — Real-data feasibility and review

The [literature evidence extension](literature-evidence.md) now supports bounded
public retrieval, preserved sources and local extraction/review drafts for D1.
Retrieval and schema checks are software evidence; live local models produced
incorrect assignments and incomplete outputs. Qualified source review, complete
methodology and scientific dataset approval remain external D1/D5 requirements.

### D1 — PCSK9 evidence assessment

Revisit original papers/patents; source-linked register of endpoints/species/constructs/methods/coverage/questions/reuse restrictions; distinguish binding vs expression/secretion/cellular effects. Assess usable counts, classes/scaffolds. **Acceptance:** written continue/separate-endpoint/pause decision. May run alongside A; qualified approval is external.

### D2 — Source completeness/release provenance

Release information where actually verified, start/end times, queries, caps, pagination status; preserve exact responses/hashes, incomplete interrupted pulls and named-bulk target extracts. Preserve Open Targets snapshots separately. **Acceptance:** complete extract vs capped sample vs release-pinned extract is explicit. Depends R3.

### D3 — Attributable structured review

Reviewer identity/date/source/rationale and comparability metadata; preserve revisions as new dataset versions; dashboard draft CSV export and explicit submission. Legacy checksums remain intact. **Acceptance:** every new approval is attributable and historic reports unchanged. Depends R3,D1. Software cannot confer credentials.

### D4 — Dataset audit

Retained/excluded reasons, structures/measurement conflicts, unspecified stereochemistry, repeated publications, counts/classes/scaffolds before/after aggregation, identical fingerprints and split feasibility. **Acceptance:** export before training and specific failures for unsuitable datasets. Depends D2,D3.

### D5 — Freeze approved dataset

Comparable reviewed activities, original values/units/IDs, immutable manifest and dataset card, development and independent candidates distinguished, recorded scientific approval. **Acceptance:** traceable/approved/technically usable real set. Depends D4. Zero usable records is valid; do not weaken exclusions to train.

## C — Scientific model evidence

### M1 — Frozen evaluation protocol

Pin versions/endpoint/activity threshold/features/assignments/metrics; retain five scaffold development holdouts; molecule/fingerprint/source overlap checks and rejected-partition reasons; reserve final test before tuning; separate activity vs classification thresholds. **Acceptance:** exact assignments/protocol reproduce. Depends R3,D4; prepare before D5.

### M2 — Baseline comparison

Dummy, logistic regression and Random Forest on identical partitions; balanced accuracy/ROC AUC/AP/confusion/prevalence; assay/scaffold/source error analysis. Fixed starting settings; tuning training-only; runs persist separately. **Acceptance:** comparison explains gains/variability, including negative results. Depends D5,M1.

### M3 — Independent/later evaluation

Score separately reviewed compatible set without refitting; remove/disclose molecule/source overlap; temporal dates from original experiments/publications rather than downloads. Record prior use in selection. **Acceptance:** honest external report or explicit unavailability. Depends M2 + independent data.

### M4 — Nearest-compound context

Tanimoto nearest training compounds, activity/assay provenance, exact-molecule/scaffold flags; development error-vs-similarity assessment; avoid unsupported applicability thresholds. **Acceptance:** interpretable reference context per score. Depends M2; synthetic UI allowed.

### M5 — Calibration if feasible

Reliability diagram/Brier/log loss, sigmoid vs raw on training-only scaffold-aware partitions, keep final test untouched; preserve raw/calibrated separately. **Acceptance:** evidence or explicit insufficiency. Depends M1,M2 + sufficient real data.

### M6 — Model card/release

Intended use/endpoint/coverage/evidence/weaknesses/prohibited interpretation; synthetic/experimental/research-evaluated statuses; explicit scoring model; older releases retained. **Acceptance:** evidence/limitations available with selected model. Depends M2–M5; unavailable evaluation remains explicit.

## D — Solo research usability

### U1 — Guided onboarding

In-app explore → optional demo → train → preview → export checklist; sources distinguished; actionable empty states. **Acceptance:** offline tutorial without code reading. Depends R4.

### U2 — Projects/collections/history

Named projects and molecule collections, notes, retrievable predictions linked to experiment/data; migrate projectless rows to default; filters/CSV export. **Acceptance:** resume research session with original inputs/results. Depends R2,R3.

### U3 — Batch processing

CSV selected SMILES column, per-row validation/duplicates/failures, configurable 1,000-row starting limit, structures-only or explicit model, explicit save. Persist job with one local worker for long requests; interruptions recoverable. **Acceptance:** mixed file produces attributed downloadable results. Depends U2,R3.

### U4 — Unified research report

Dataset audit, reviews, evaluation and selected-molecule results with IDs/checksums/notices; Markdown/JSON/CSV package; always selected history. **Acceptance:** export reconstructs a shortlist's reasoning. Depends U2,D4,M6.

## E — Additional targets

### X1 — Rank candidates

Source-linked cardiovascular target comparison: relevance/comparability/data/class-scaffold diversity/licensing. **Acceptance:** user-selected target and approved endpoint/data path. Depends D1 and feasibility outcome.

### X2 — Target/endpoint configuration

Remove PCSK9 hardcoding via explicit target configurations, target-specific chemistry/threshold/compatibility; preserve PCSK9 versions and forbid cross-target mixing. **Acceptance:** PCSK9 regression suite passes plus configurable second target. Depends X1,R3,M1.

### X3 — Second supported target

Repeat review/audit/evaluation/model card; target selector/readiness; no unsupported combined score. **Acceptance:** documented independent target workflow. Depends X2 + approved data.

## F — Private collaboration

### P1 — Ownership/sharing

Workspaces/memberships/project ownership; owner/editor/viewer; scope datasets/models/predictions/exports/jobs; migrate existing owner data. **Acceptance:** sharing plus preserved solo records. Depends U2,R2,R3.

### P2 — Authentication/authorization/audit

OIDC hosted login, API checks on every resource, recorded imports/reviews/training/exports/membership; local mode confined to local use; cross-tenant ID/file tests. **Acceptance:** roles and isolation verified. Depends P1.

### P3 — Private deployment

Tagged Docker Compose on one server/PostgreSQL/HTTPS/private DB; secrets, volumes, automated backups/restore, logs/health/disk alerts, upgrade/rollback. Keep Streamlit unless evidence supports replacement. **Acceptance:** invited access + recovery drill. Depends P2,R5; provider/identity/region/budget selection BEFORE provisioning, local preparation free.

### P4 — Private pilot

User-authorized invitations, observe research workflow, record confusion/scientific interpretation/cost; resolve release blockers. **Acceptance:** evidence-backed product investment decision. Depends P3 + labelled model evidence.

## G — Commercial research service

### C1 — Customer/offer

Pilot-defined audience/workflow/targets/usage/support/pricing; redistribution/commercial permissions; terms/privacy/retention/deletion with appropriate advice. **Acceptance:** written offer based on actual needs. Depends P4.

### C2 — Commercial operations

Organization onboarding/invites, usage/quotas/admin; approved pricing/payment arrangement before billing; export/deletion/backup retention; billing never bypasses authorization. **Acceptance:** test organization onboard/use/export/close. Depends C1,P2.

### C3 — Limited paid beta

Security/recovery/operational gates, supported capability/limits, support/incident process, usage/cost/reliability monitoring, bounded access. **Acceptance:** sustainable small-customer operation. Depends C2 + approved release checklist. Research software sales do not validate drug efficacy.

## Interface and acceptance commitments

Future CLI: `cvti doctor`; `cvti backup create|inspect|verify|restore`; `cvti datasets audit ID`; `cvti evaluate --experiment-id ID --dataset-version-id ID`. Add prediction history, batch jobs, and workspace/project interfaces as their tasks land. Keep current local endpoints backwards compatible; migrations/additive provenance first, documented versioning for altered meanings/access.

Regression gates: installations/migrations/backups/relocation/corrupt artifacts; capped/interrupted sources/review gaps/conflicts/empty review; deterministic splits and no training/calibration use of final test; dashboard selection/saving/history/export; mixed batch limits/interruption; authorization/isolated downloads; deployment/recovery/rollback; quotas/billing test events/export/deletion/isolation.

## Order and gates

R1 → R2/R3/R4 → R5 → D1–D4 → M1 → D5 → M2–M6. U tasks can proceed while science waits. X1 can investigate alternatives when PCSK9 is insufficient. Then private P1–P4 and commercial C1–C3, with X expansion conditional on selected target/data.

Real training needs approved comparable data/audit/protocol. Independent claims need untouched compatible data. Hosted private access needs ownership/authentication/authorization. Spending needs explicit providers/budget. Commercial beta needs pilot/licensing/operations evidence. When a gate cannot pass, record the reason and continue independent useful work.

Separate future plans: validated endpoint-specific ADMET, benchmarked docking, qualified laboratory experiments, molecular generation after evaluation exists. They are outside the initial implementation.

## Market-informed local workflow extensions — 18 October 2026

The user requested development based on the commercial/open-source workflow
research while retaining the earlier local-workflow focus. The implementation
scope and usage are in [the integrated workflow guide](integrated-research-workflow.md).
These additions extend U2–U4 without satisfying D5 or scientific model gates:

- **L1 — Material identity:** project-scoped registered compounds, explicit
  modality, chemistry policy/version, original structures, batches and samples.
- **L2 — Staged registration:** CSV mapping, row validation, retained input/plan
  hashes, explicit atomic submission and idempotent history.
- **L3 — Assay records:** immutable protocol/run context and material-linked raw
  observations, origin/unit/modality checks and append-only corrections. All
  remain unreviewed outside the training dataset path.
- **L4 — Candidate workbench:** descriptor/structure filters, saved criteria,
  source inspection, explicit read-only model previews and per-candidate errors.
- **L5 — Portable evidence:** selected-project export with original inputs,
  correction history, checksums and backup/restore preservation.

No new predictor architecture, pretrained checkpoint, external inference,
generative engine, synthesis planner or infrastructure is implied by these tasks.
Those need a concrete scientific use case, compatible data and their own gates.

## KMed-informed discovery workbench — 22 October 2026

The user authorized implementation of the practical recommendations from the
KMed comparison. The [discovery workbench guide](discovery-workbench.md) defines
the delivered scope and exact limitations:

- **K1:** Rich molecule dossier, chemistry alerts, local conformer viewer/SDF,
  structural screening and explicit navigation between molecule workflows.
- **K2:** Nine typed ADMET endpoints; optional pinned local pretrained inference;
  immutable model manifests, checksum and identity checks, explicit unknown
  applicability/calibration/overlap. Experimental release only.
- **K3:** Explicit public target context and raw source snapshots; prepared
  receptor Vina jobs with provenance, settings, poses and local visualization.
- **K4:** Unit-aware dose-response analysis, plate QC, compatible same-assay SAR,
  transparent analog enumeration and diversity selection.
- **K5:** Additive scientific run history, durable worker jobs, checksums,
  failure/interruption handling and explicit new-run retry.

These software tasks do not satisfy D5 or validate any PCSK9 or ADMET predictor.
Independent endpoint evaluation and PCSK9-specific redocking remain required
before making scientific performance claims. Full matched molecular pairs,
feedback-trained active learning, PBPK, Boltz, free energy, binder design and
virtual-cell modeling remain separate evaluated extensions; no heuristic
placeholder is labeled as one of those capabilities.
