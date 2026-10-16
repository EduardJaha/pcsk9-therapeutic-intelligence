# PCSK9 Lab 0.2.0 — dependable local research workflow

Release date: 2026-10-16. Local, solo operation; no hosting or billing activated. Full roadmap/status: [progress](progress.md).

## Delivered

- GitHub offline/SQLite and PostgreSQL gates, including preserving migrations and installed-package smoke verification.
- Checksummed backup/create/inspect/verify/restore with model-path relocation, source preservation and stopped-writer guards.
- Training code/environment/model/feature/seed provenance, exact evaluation assignments, atomic artifacts and pre-load integrity checks. Legacy unknowns remain unknown.
- Read-only diagnostics and one foreground launcher for API, Streamlit and one durable CSV worker, plus OS launch helpers.
- Complete/incomplete/capped source snapshot metadata, exact response-body preservation, named target-extract import and separate bounded Open Targets snapshots.
- Attributable review fields, an explicit draft/submission workflow and exportable pre-training data audits.
- Frozen development protocols, fixed dummy/LR/RF comparison, nearest-compound context, raw-score calibration diagnostics, model cards and an existing-model evaluation command.
- Local projects, notes, collections, prediction history, selected-result research ZIPs and resumable CSV jobs with explicit saving.
- A 23-assay evidence register and documented real-data feasibility gate. No historical exclusions were reversed and no real model was trained.

## Upgrade your existing checkout

Stop all old API/dashboard/worker processes first (Ctrl+C in their terminals). From the repository with `.venv` activated:

```bash
uv sync --frozen --extra dev
cvti db upgrade
cvti doctor
cvti start
```

Open http://127.0.0.1:8501. Ctrl+C in the launcher terminal stops all three components. After updating source, restart Streamlit too: imported helper modules can otherwise remain cached. The API's old manual `--reload` command does not restart the separate Streamlit process.

Existing datasets/experiments/predictions remain; the project migration assigns earlier experiments/predictions to Local project. New provenance columns are null for old models because their environment/history cannot be reconstructed reliably. No demo data is loaded by upgrade/startup.

Use [the workflow guide](research-workflow.md) for projects, review submission, CSV jobs and exports; [operations](operations.md) for recovery. Backup archives are local, intentionally ignored by Git. They include trusted executable model artifacts; checksums establish integrity, not who authored an archive.

## Verification

- 34 local tests passed with PostgreSQL enabled; no live biomedical APIs were needed.
- SQLite and PostgreSQL creation, preserved upgrades, fixture training/prediction and relocated recovery verified.
- Empty/populated dashboard pages and completed batch view tested; project/history and batch screens inspected in the browser.
- Real CLI + API + dashboard + worker + mixed CSV + relocated restore smoke passed, including fresh non-editable installation from a clean checkout.
- Restored model SHA-256 and prediction matched. Current user's demonstration records were preserved.
- GitHub checks for [the release implementation](https://github.com/EduardJaha/pcsk9-therapeutic-intelligence/actions/runs/38889540407) passed both jobs.

macOS and Linux/GitHub were executed. Windows helper and process handling are supplied; a Windows machine was not available for native verification. The upstream Starlette/httpx TestClient deprecation remains a warning.

## Still gated

There is no qualified assay reviewer yet. Real dataset approval, real baseline acceptance, calibration, independent/temporal scientific evidence and research-evaluated model release remain pending. Existing scores are synthetic demonstrations or uncalibrated experimental outputs. New evaluation commands do not supply missing independent data.

Shared workspaces, OIDC/roles/tenant isolation, hosted pilots, customer/billing workflows and additional targets remain roadmap work. Local project grouping is not multi-user security. Do not expose this unauthenticated development service publicly. The user's selected release policy is local use with no hosting cost.
