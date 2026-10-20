# Local operation and recovery

## Start and diagnose

From the repository with the environment activated:

```bash
cvti doctor
cvti start
```

`cvti start` owns the API, dashboard and one CSV worker. Ctrl+C stops all three. Existing occupied ports are reported rather than replaced. Use `cvti start --api-port 18000 --dashboard-port 18501` for alternatives. The dashboard API connection is set automatically. Shell helpers: `./scripts/start.sh` (macOS/Linux) or `./scripts/start.ps1` (PowerShell). Both assume the documented `.venv` already exists.

`cvti doctor` does not upgrade the schema, load fixtures or save predictions. It reports schema revision, missing/corrupt artifacts and server status. Old models whose hashes were never recorded are labelled legacy-unverified; do not invent missing training history. Run `cvti db upgrade` with servers stopped if an upgrade is needed.

### Windows startup lock error

If `cvti start` exits with `msvcrt.locking` / `PermissionError: [Errno 13]`
and then says the workspace is in use, update to the Windows shared-lock fix.
The earlier CRT lock treated API and worker access as exclusive, causing them to
block each other. The fix uses Windows `LockFileEx` shared locks while retaining
exclusive maintenance and single-worker locks. Do not delete lock files or disable
locking to work around this error.

After updating, restart from PowerShell in the project directory:

```powershell
.\.venv\Scripts\python.exe -m cvti.cli start
```

Keep that window open, then visit `http://127.0.0.1:8501/` on the same PC.

Until the fix is installed, you can run the API and dashboard separately without
starting a CSV worker. In one PowerShell window in the project directory:

```powershell
.\.venv\Scripts\python.exe -m uvicorn cvti.api:app --host 127.0.0.1 --port 8000
```

In a second PowerShell window in the same directory:

```powershell
$env:API_URL = 'http://127.0.0.1:8000'
.\.venv\Scripts\python.exe -m streamlit run dashboard.py --server.address 127.0.0.1 --server.port 8501
```

Keep both windows open. CSV batch jobs will remain queued until a worker runs;
do not start one alongside the old API before installing the shared-lock fix.

## Back up

Stop API, dashboard and all writers first. Do not use backup concurrently with an old version of the API or external database clients. New API and CLI writers cooperate through a process lock; this cannot detect unrelated applications or another computer writing PostgreSQL.

```bash
cvti backup create --output ../pcsk9-backup.zip --services-stopped
cvti backup inspect ../pcsk9-backup.zip
cvti backup verify ../pcsk9-backup.zip
```

The archive contains the database, every referenced model and retained JSON/CSV/Markdown inputs/exports below the data directory. Dataset snapshots/reviews also reside inside the database. It does not contain `.env`, credentials, the Python environment, arbitrary sibling directories or other backups. Missing model files prevent backup rather than silently creating an incomplete recovery set. Archive checksums detect accidental corruption, not authenticity; restore only your trusted archives. Keep a separate copy on storage you control. GitHub contains source code, not local research records.

## Restore into a different directory

```bash
cvti backup restore ../pcsk9-backup.zip --destination ../pcsk9-recovered --services-stopped
```

All members and checksums are verified before extraction. The restored directory contains `.env.restored` with the new database/artifact paths. Copy those two settings into the repository's `.env` while services remain stopped, then run `cvti doctor` and `cvti start` from the source repository. Keep the original workspace untouched until recovery is verified. Archived model paths are remapped to the recovery directory.

An existing destination is rejected by default. `--replace` preserves it under a `.previous-...` sibling before publishing the restored directory. Never restore over the source repository. The backup manifest describes the original files; restored DB bytes differ because model paths were relocated. Dataset manifests and model file hashes remain unchanged.

## PostgreSQL

Install matching `pg_dump`/`pg_restore` tools and place them on PATH. Backups use a custom-format database dump without ownership/privilege grants. Passwords are passed through the child environment, not command-line arguments or manifests. Restoring requires an existing, empty destination database:

```bash
cvti backup restore ../postgres-backup.zip --destination ../pcsk9-pg-recovered --database-url 'postgresql+psycopg://USER:PASSWORD@HOST:5432/NEW_DATABASE' --services-stopped
```

Use your shell's environment/configuration facilities for secrets where practical; command history may store a URL you type. Restore never drops an existing PostgreSQL database. SQLite↔PostgreSQL conversion is not a backup operation.

## Automated checks

GitHub's Tests workflow installs Python 3.12 with `uv sync --frozen --extra dev` and runs the offline suite plus a PostgreSQL service job. Locally:

```bash
python -m pytest -q
# Optional, against a dedicated disposable PostgreSQL test database:
TEST_DATABASE_URL=postgresql+psycopg://USER@127.0.0.1:5432/cvti_test python -m pytest -q tests/test_db_backends.py tests/test_backup.py
```

PostgreSQL tests use temporary schemas and separate temporary recovery databases, and need permission to create/drop those test objects. Never use a production database URL for tests. No biomedical HTTP service is required.


## CSV worker

`cvti start` and Docker Compose now include one persistent local worker. If you start API/Streamlit manually in two terminals, start a third with `cvti worker`. `cvti worker --once` processes at most one queued job and exits. Jobs live in the database, not browser memory. Completed rows and any saved predictions commit together. Restarting the worker marks previously running jobs interrupted; use **Retry remaining batch rows** explicitly. Stop the worker too before backup or schema maintenance. A separate process lock prevents two local workers sharing the same configured workspace.

## API maintenance locks

The current API and CLI writers hold shared workspace locks. Schema upgrades and backups require an exclusive lock. This permits API requests and a CSV worker to coexist while preventing a backup or migration from claiming exclusivity over active cooperative writers. External database clients are outside this mechanism. Current schemas are checked without migration; new schemas upgrade under an exclusive lock before services start.
