# Roadmap progress — local release 0.2

Updated 2026-10-17. Task definitions: [approved roadmap](roadmap.md). User decisions: **no qualified reviewer yet; keep this release local with no hosting cost**. These decisions gate real-data approval and hosted/commercial work. Software acceptance and scientific evidence are reported separately.

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
