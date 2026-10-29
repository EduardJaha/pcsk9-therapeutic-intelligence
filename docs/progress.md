# Roadmap progress — local release 0.2

Updated 2026-10-28. Task definitions: [approved roadmap](roadmap.md). User decisions: **no qualified reviewer yet; keep this release local with no hosting cost**. These decisions gate real-data approval and hosted/commercial work. Software acceptance and scientific evidence are reported separately.

## Broader local training and program verification — 28 October 2026

Two further 1.7B QLoRA candidates completed two epochs/56 optimizer updates each
on 224 frozen software examples. Validation compared the base, current assistant,
both adapters and the installed 4B reference using production JSON constraints.
The 4B reference won validation (24/48) but failed the reserved-test promotion
rule (16/48 versus the current assistant's 23/48). The current
`pcsk9-assistant:continued-20261027-02` remains active. No test-driven tuning or
alternate-candidate deployment followed. See [protocol, results and limitations](assistant-evaluation.md).

Full Windows offline suite: **117 passed, 4 PostgreSQL checks skipped**, with the
existing Starlette/httpx deprecation warning. The real CLI/API/dashboard/worker
and relocated backup/restore smoke passed. Windows SQLite snapshot handles now
close explicitly; backups prune reserved runtime/training directories. Six
discovery pages were opened with their content headings verified in the browser.

The optional Windows discovery environment was installed from the existing
lockfile in `data/runtime/discovery/`. Actual ADMET-AI inference returned all
nine selected endpoints for aspirin in a disposable database. Vina 1.2.7
completed the version-pinned upstream 1IEP/ABL1 tutorial with three poses; this
does not validate PCSK9 docking. Scientific smoke checks used CPU while the GPU
was reserved for language-model work. Open Targets PCSK9 and RCSB retrieval also
succeeded with raw response hashes. These are integration checks, not measured
ADMET accuracy, calibration, receptor suitability or clinical validation.

Training examples and smoke records stayed outside the user's research data.
Real biomedical source leads remain excluded from training pending source,
reuse-rights and qualified scientific review. No assay approvals or new
PCSK9 numerical predictor were produced. Historical runs and raw reports remain
under ignored `data/assistant-training/`; code and reports describe failures as
well as successes.

Final connection check: API/dashboard/worker are running with the verified
Windows discovery paths. Registered one experimental installed ADMET release
metadata record; every research table count stayed unchanged. Both assistant
models passed 8/8 live application cases. The retained model answered through
the running API with 2,893,860,044 GPU bytes observed, and the browser displayed
its cited draft. Dataset/adapter/merged-export checksums and both final
two-epoch/56-update schedules passed the closing integrity audit. Detailed
report: `data/assistant-training/2026-10-28-evidence-v4/REPORT.md`.

## Local assistant training pilot — 27 October 2026

Continuation `2026-10-27-continued-02` completed and activated as
`pcsk9-assistant:continued-20261027-02`. One additional epoch of the same frozen
200 documentation examples at learning rate 0.00001 brings cumulative exposure
to two passes/50 optimizer steps. The saved adapter was loaded with a fresh
optimizer and schedule; parent weights, manifests, original source snapshots,
dataset assignments and reports remain preserved.

Validation-only selection: loss on the same 16 examples decreased from
0.0045478423 to 0.0008687152, with all eight selected validation generation
exercises passing the mechanical checks. Historical test outputs were not used
to select this continuation. Both exported models passed the same six synthetic
application regression cases against a disposable database. Eight offline script
tests passed. A live request after activation returned the new model/digest and
showed approximately 2.9 GB of GPU allocation, with unchanged research summary.
No new biomedical examples or scientific accuracy claims were added. The
original model tag remains available for rollback. Detailed manifests, logs and
report: `data/assistant-training/2026-10-27-continued-02/`.

Follow-up connection completed: the local ignored `.env` selects the trained
pilot and its separate local store on port 11435. `cvti start` can now start the
cloud-disabled Ollama runtime alongside the application, with readiness checks,
reuse of an existing compatible service and cleanup of owned children. An actual
request through the running app returned a cited draft with approximately
2.9 GB of GPU allocation observed; its model/evidence provenance was recorded
and the research summary stayed unchanged. The model unloads after answers.
Forty relevant offline checks passed, including new mocked startup, missing
runtime/model, port ownership and failure-cleanup cases. Scientific validation
remains unestablished. See the [connected assistant guide](pretrained-assistant.md).

On `codex/local-assistant-finetuning`, the user requested local Unsloth training.
An optional script prepared documentation-derived software-behavior exercises
and trained a Qwen3 1.7B QLoRA adapter with the existing local CUDA runtime. The
application's locked environment and research database were not changed by
training. All weights, generated examples, source snapshots, logs and reports
remain under ignored `data/assistant-training/2026-10-27-pilot/`.

- 200 training/16 validation/24 held-out examples, split by source document;
  one epoch, 25 optimizer steps, 128 seconds of actual training after compilation.
- Frozen inputs, model/config hashes, exact evaluation assignments, original
  outputs and adapter/export identity retained. Twelve selected template checks
  passed. Raw baseline formatting scores are not comparable to the existing
  app's constrained decoder; no scientific improvement is established.
- Local Q8_0 export registered in a separate cloud-disabled Ollama store.
  Six live assistant checks passed against a disposable database, with no change
  to its research summary. No assay approvals or molecular predictions created.
- 37 relevant offline tests passed; five script checks passed again after export
  fixes. Windows compilation/test operations required native execution outside
  the command sandbox. Initial export failures and successful retries are logged.

See [training and startup instructions](local-assistant-training.md). These are
programmatically generated examples and small synthetic integration checks,
not expert-reviewed biomedical training or independent scientific evaluation.
The real-data review and molecular-model gates below remain in place.

## KMed-informed discovery workbench — 22 October 2026

Implemented on `codex/integrated-discovery-workbench`. See the
[discovery guide](discovery-workbench.md) for setup, endpoint contracts, use and
scientific limits.

- Sidebar pages are organized under Workspace, Compounds, Predictions & design,
  Assays & evidence, and Models & processing. One current-page highlight is
  preserved across groups, bookmarked links, refresh recovery and molecule
  handoffs. Follow-up verification: all 18 dashboard/discovery tests passed;
  the running browser was checked for grouped navigation and active selection.
- Rich molecule dossier with 13 RDKit properties, PAINS/BRENK flags, rule checks,
  deterministic ETKDG/MMFF conformers, an offline interactive viewer and SDF.
- Nine experimental ADMET-AI endpoint contracts; immutable release manifests;
  local queued inference with checkpoint/version/identity/range checks. No
  synthetic fallback, calibrated-confidence claim or clinical composite score.
- Public target dossiers preserving original responses/hashes; local Vina jobs
  with prepared receptor inputs, target/pocket rationale, reproducible settings,
  ligand preparation, engine/executable hashes and downloadable poses.
- Dose-response fitting with explicit units, retained replicates and quality
  warnings; plate QC; strict same-assay activity-cliff analysis; structural
  screening and transparent analog proposals with a diversity shortlist.
- Seven new pages and shared worker integration. Saved scientific runs are
  project-scoped and checksummed. Failed/interrupted runs require explicit retry,
  which creates a linked new run and preserves the previous failure.
- Optional environment installed locally under ignored `data/runtime/discovery`:
  ADMET-AI 2.0.1, Meeko 0.8.0 and transitive versions recorded in
  `requirements-discovery.lock`. Official macOS arm64 Vina 1.2.7 installed under
  `data/runtime/vina`. Weights and runtime artifacts are not tracked in Git.
- **Verification: 94 passed, 4 skipped** in the full offline suite; PostgreSQL
  tests skipped because `TEST_DATABASE_URL` was not configured. Existing SQLite
  preservation/schema/backup tests and new project isolation, output rejection,
  provenance, curve units, SAR compatibility and page navigation tests passed.
  `git diff --check` passed.
- Real integration checks, separate from the offline suite: ADMET inference on
  public aspirin returned all nine selected endpoints through the browser and
  worker; Vina returned three poses against the upstream 1IEP tutorial receptor;
  Open Targets PCSK9 and RCSB 6U26 retrieval succeeded. These are integration
  checks, not independent scientific benchmarks. Browser inspection covered the
  dossier, 3D rendering, navigation and completed endpoint result display in an
  isolated verification database.
- Before upgrading the user's workspace, created and verified
  `data/backups/pre-discovery-2026-10-22.zip`. Applied the additive
  `f51d7a64b208` migration and verified identical row counts in all 19 pre-existing
  tables. No example compounds, assays, predictions or scientific test runs were
  inserted into the user's workspace. Registered the installed model as an
  experimental local release and started API/dashboard/worker locally.
- Independent ADMET validation, endpoint-specific training overlap, calibrated
  uncertainty, PCSK9 receptor/pocket validation, measured feedback learning,
  PBPK, Boltz/FEP, binder and virtual-cell models remain unestablished. Existing
  assay-review and D5 training gates remain intact.

## Integrated registry and research workflow — 18 October 2026

The user requested further development based on the deeper commercial and GitHub
research. Work is on `codex/integrated-research-workflows`; the
[workflow guide](integrated-research-workflow.md) maps source patterns to the
delivered local features and documents all interfaces and limits.

- **L1/L2:** project-scoped compound identities with original structures, explicit
  modality, chemistry policy/RDKit version and descriptors; material batches and
  samples; CSV column mapping and retained input/plan checksums; per-row validation,
  explicit atomic registration and idempotent import history.
- **L3:** PCSK9 protocol/run/sample-linked observations with endpoint/readout/units,
  species/constructs/method/conditions and attributable sources. Cross-project,
  origin, modality and unit mismatches are rejected. Corrections are new records
  with rationale and links to retained originals. All observations remain
  unreviewed outside the curated training path.
- **L4/L5:** candidate descriptor/structure filters, saved criteria with integrity
  checks, property plots, direct source/observation inspection, explicit read-only
  model previews with per-candidate errors, and project ZIP exports retaining
  original CSVs, observation history and file checksums. Existing backups preserve
  registry/import records after relocation. Three new Streamlit pages have empty
  and populated navigation coverage.
- The additive `e40c6d53a934` migration preserves existing records and supports both
  database backends. It was exercised only in temporary test workspaces; the user's
  research database was not upgraded or populated during development.
- Verification: **76 passed, 4 skipped** in the full offline suite. PostgreSQL
  integration/restore checks were skipped because `TEST_DATABASE_URL` was not
  configured. SQLite preserving migrations, schema/ORM parity, staged import
  rollback, source/scoping checks, corrections, read-only scoring, exports,
  relocated backup recovery, consistent export snapshots during concurrent writes,
  and the dashboard workflow passed. Browser inspection
  used real local API/Streamlit servers with synthetic records in a temporary
  workspace; candidate/assay/registry pages rendered. Temporary servers were stopped.
- No model weights or external models were downloaded, no new predictor was
  evaluated, and no scientific assay approval or real-data model acceptance was
  inferred. The D5/M gates and hosting decisions below remain in effect.

## Local collection search — 18 October 2026

- A [focused market workflow review](market-workflow-review.md) compared documented CDD Vault, DataWarrior, Benchling and KNIME workflows. The selected gap was read-only structure search in the existing local collections page.
- Exact, substructure and Morgan fingerprint Tanimoto similarity search now operate within the selected project, with optional collection scope, stable result ordering, source entry IDs, notes, counts and displayed-results CSV export. Search does not add predictions, measurements or reviews.
- This is structural retrieval only. No model quality, PCSK9 activity, assay comparability or applicability claim follows from a match. Saved queries, sketching and enterprise workflow features remain outside this pass.
- Verification: the full offline suite passed (**66 passed, 3 skipped**; PostgreSQL test database not configured), including API project isolation and Streamlit form coverage. `git diff --check` passed. A live browser session against the user's database was not exercised.

## Browser refresh recovery — 17 October 2026

- Local recovery snapshots preserve the selected page, project, model, submitted
  molecule inputs and displayed profile/comparison results across a fresh browser
  session. URLs carry an opaque workspace identifier; research content stays under
  ignored `data/workspaces/`. A URL without that identifier starts blank.
- Restoring a snapshot repeats no profile, comparison or prediction requests and
  creates no research records. Invalid submissions clear persisted results;
  switching projects clears molecule inputs and output. Snapshot integrity and
  atomic writes protect against partial/corrupt recovery files, with visible
  warnings for read/write failures. Assistant drafts are not persisted.
- Regression coverage uses fresh Streamlit sessions with retained URLs, temporary
  databases and temporary recovery files. Offline suite: **64 passed, 3 skipped**
  (PostgreSQL test database not configured). Direct Chrome interaction was not
  exercised; refresh is simulated by discarding all Streamlit session state and
  reusing only the URL. Scientific capabilities are unchanged.

## Pretrained assistant addition — 17 October 2026

The user authorized starting with existing trained models, requested a dedicated
branch and repository `AGENTS.md`, and authorized pushing the changes. Work is on
`codex/pretrained-research-assistant`. The first delivered integration is a local
language-model evidence assistant; a pretrained molecular predictor is a separate
future milestone subject to endpoint/data evaluation.

- Added explicit evidence selection, deterministic excerpt retrieval, local Ollama
  status/inference, structured claims and source/passage references resolved to
  original quotes. Source hashes, model digest and generation settings accompany
  the downloadable draft. Citation checks do not establish scientific entailment.
- Added **Research assistant** to Streamlit, source previews, model setup guidance,
  quoted claims, evidence gaps and JSON download. Failed submissions clear old
  results. The assistant has no tools and writes no research records.
- Installed an isolated official Ollama runtime locally (v0.40.5; release archive
  SHA-256 verified) and downloaded `qwen3:1.7b` into ignored `data/ollama/`.
  Model digest: `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`.
  This is a small general language model, not a scientifically evaluated model.
- A real local-model request through FastAPI returned a cited draft about the
  project feasibility assessment in approximately five seconds. Original Unicode
  passages were retained. Testing used a temporary database and no imported
  measurements. This verifies integration only, not biomedical research quality.
- The existing CLI/API/dashboard/worker/relocated-restore exercise passed. Offline
  suite: **57 passed, 3 skipped** (PostgreSQL test database not configured).
  Tests cover source isolation, quotes, model availability/replacement, invalid
  output, project selection, disabled/cloud configuration and dashboard behavior.
- The user cleared the research workspace on 17 October. Earlier populated-workspace
  verification below is historical; no demo records were restored by this work.

Setup, boundaries and API details: [pretrained assistant guide](pretrained-assistant.md).
Real-data assay approval, independent molecular evaluation and hosting remain
unchanged dependencies.

| Task | State | Delivered / exact remaining requirement |
|---|---|---|
| R1 | Verified complete | GitHub SQLite/offline and PostgreSQL migration/vertical-slice/restore jobs pass ([verified run](https://github.com/EduardJaha/pcsk9-therapeutic-intelligence/actions/runs/38889540407)). Expanded release checks also run on subsequent pushes. |
| R2 | Verified complete | Create/inspect/verify/restore, original checksums/schema/version, stopped-writer guards, SQLite/PostgreSQL relocation, preserved records and tamper/path tests. Current workspace backed up locally; no research data pushed. |
| R3 | Verified complete | Additive legacy-preserving migration; code/environment/library/parameters/features/seed provenance, exact assignments, atomic writes and pre-load checksum verification. Existing old experiment retains explicitly unknown metadata. |
| R4 | Verified complete | Read-only doctor; occupied-port messages; foreground API/dashboard/worker launcher, Ctrl+C cleanup, Windows/macOS/Linux helpers. Launcher/recovery smoke test passes locally. Windows helper is supplied; Windows was not executed on this Mac. |
| R5 | Verified complete | Full native PostgreSQL suite, empty/populated dashboard, real CLI/service/restore exercise, and a fresh checkout installed without editable source all passed. GitHub also verifies installed-package recovery. Documented v0.2.0 release. Docker engine unavailable on this Mac; PostgreSQL container exercised in GitHub. |
| D1 | In progress | [Feasibility assessment](pcsk9-feasibility.md) and [23-assay evidence register](../reviews/pcsk9-evidence-register.csv) delivered. Recommendation: pause real training. Original protocols, potential usable coverage, reuse terms and qualified sign-off remain unresolved. |
| D2 | Verified complete | Schema-2 snapshots preserve exact response bytes/hashes, timing, observed release/caps/completion; capped/interrupted pulls retained and blocked from curation. Named target JSON bulk-extract importer preserves original bytes and supplied release attribution; separate bounded Open Targets context snapshots. New cases tested with mocked HTTP. |
| D3 | Verified complete | New approvals require reviewer/date/primary-source/constructs/method/conditions. Browser drafts do not curate until explicit submission. Historical manifests preserved; software tests verify revisions. This is recorded attribution, not expert credential verification or real assay approval. |
| D4 | Verified complete | CLI/API/dashboard export audit: raw/retained/aggregated class/scaffold counts, exclusions/conflicts/stereo/fingerprint/source overlaps and split feasibility. Software feasibility only; no real-data approval inferred. |
| D5 | Waiting on dependency | Zero approved comparable real measurements. Need original sources and qualified assay review before freezing a scientific dataset. |
| M1 | In progress | Frozen checksummed development protocols, exact partitions, feature compatibility, molecule/scaffold/fingerprint checks and source-overlap disclosures implemented/tested. Final independent set cannot yet be reserved; no tuning enabled. |
| M2 | Waiting on dependency | Dummy/LR/RF comparison software and dashboard implemented; shared protocol verified on synthetic fixtures. Real baseline acceptance requires D5. |
| M3 | Waiting on dependency | Existing-model evaluation CLI implemented/tested, no refit, overlap removal/source checks/date validation/prior evaluation history. No suitable real independent/later dataset exists; reports state this explicitly. |
| M4 | In progress | Nearest compounds with activity/assay/document references and development error-vs-similarity summaries implemented. Scientific applicability/error study waits for approved real data. No applicability cutoff claimed. |
| M5 | Waiting on dependency | Raw Brier/log-loss/reliability diagnostics implemented. Sigmoid calibration not fitted: no sufficient approved training-only calibration dataset. Scores remain uncalibrated. |
| M6 | In progress | Synthetic/experimental model cards with provenance/evaluation/limitations visible in models and prediction screens. No research-evaluated release assigned without scientific evidence. |
| U1 | Verified complete | In-app first-session guide, empty-state guidance, explicit sources; demo remains optional. Empty and populated navigation tested. |
| U2 | Verified complete | Local projects, notes, named collections, structure deduplication, paginated/filterable prediction history, CSV export; old records assigned to Local project. This is not multi-user sharing. |
| U3 | Verified complete | CSV column choice, configurable 1,000-row starting limit, explicit score/save, durable one-worker jobs, per-row outcomes, transactional checkpoints and explicit retry. Resume test proves no duplicate saved predictions. |
| U4 | In progress | Selected experiment/prediction ZIP includes Markdown/JSON report, audit, model card, reviews, project notes, CSV and manifest hashes. Software verified; final real-model evidence depends on M6. |
| X1 | Waiting on dependency | No additional target selected. Complete PCSK9 feasibility/source review, then user selects from a sourced target comparison. No target switch performed. |
| X2–X3 | Waiting on dependency | Await explicit target/endpoint selection and reviewed data; PCSK9 rules remain intact. |
| P1–P2 | Not started | Release intentionally stays solo/local. Shared workspaces, memberships, OIDC, role enforcement and tenant isolation remain future work; no authorization claim made for local project grouping. |
| P3–P4 | Waiting on dependency | Hosting intentionally deferred; providers, identity setup, region, budget, deployed auth and user-authorized pilot recruitment unavailable. |
| C1–C3 | Waiting on dependency | Need private pilot evidence, commercial-use review, terms/pricing/payment decisions and release gates. No billing or commercial hosting activated. |

## Verification evidence

- Full local test run including native PostgreSQL: **34 passed** (schema/migrations/backup/provenance/HTTP mocks/review history/protocols/baselines/projects/jobs/dashboard).
- Fresh checkout at the release code: installed from the lockfile with `--no-editable`; real CLI/service/recovery smoke **passed**.
- `python scripts/release_smoke.py`: real CLI + API + Streamlit + worker + checkpointed mixed CSV + relocated restore **passed**; restored model checksum and output matched.
- GitHub Actions: both SQLite and PostgreSQL green after fixing service health-check quoting. The workflow also verifies a non-editable installed package with the release smoke script.
- Current user workspace: original 24 synthetic measurements, two evidence rows, one dataset version, one experiment and one prediction preserved; default local project added by migration. No new demo data loaded into this workspace during implementation.
- Remaining warning: upstream Starlette TestClient/httpx deprecation; it does not fail the suite.

## Next meaningful work

Use the new local workflow and obtain original assay protocols plus a qualified reviewer. Continue D1/D5 only with attributable evidence. Calibration/independent scientific validation cannot be claimed from synthetic fixtures. When ready to expand, request X1. Hosting remains off until explicitly reactivated with provider/identity/region/budget choices.
