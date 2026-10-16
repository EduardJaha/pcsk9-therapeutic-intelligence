import argparse
import json
import sys
from pathlib import Path
from sqlalchemy import select, text

from cvti.curation import curate_snapshot, fetch_snapshot, write_review_sheet
from cvti.db import init_db, make_engine, session_factory
from cvti.ingest import SourceUnavailable, ingest_fixture, ingest_live
from cvti.ml import predict, train
from cvti.models import DatasetVersion
from cvti.provenance import verify_version, version_summary


def main():
    parser = argparse.ArgumentParser(description="PCSK9 research MVP")
    sub = parser.add_subparsers(dest="command", required=True)
    db_parser = sub.add_parser("db", help="Create or upgrade the configured database")
    db_parser.add_argument("action", choices=["upgrade"])
    ingest_parser = sub.add_parser("ingest", help="Load synthetic fixture or live public data")
    ingest_parser.add_argument("--source", choices=["fixture", "live"], default="fixture")
    chembl_parser = sub.add_parser("chembl", help="Snapshot and review ChEMBL PCSK9 assays")
    chembl_sub = chembl_parser.add_subparsers(dest="action", required=True)
    snapshot_parser = chembl_sub.add_parser("snapshot", help="Save raw ChEMBL activities and assay metadata")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    sheet_parser = chembl_sub.add_parser("review-sheet", help="Make a manual assay review CSV")
    sheet_parser.add_argument("--snapshot", type=Path, required=True)
    sheet_parser.add_argument("--output", type=Path, required=True)
    curate_parser = chembl_sub.add_parser("curate", help="Import only reviewed, quality-checked activities")
    curate_parser.add_argument("--snapshot", type=Path, required=True)
    curate_parser.add_argument("--review", type=Path, required=True)
    train_parser = sub.add_parser("train", help="Train scaffold-split IC50 baseline")
    train_parser.add_argument("--source", choices=["synthetic_fixture", "chembl_curated"], default="synthetic_fixture")
    train_parser.add_argument("--dataset-version-id", type=int)
    datasets_parser = sub.add_parser("datasets", help="Inspect or recover stored dataset versions")
    datasets_sub = datasets_parser.add_subparsers(dest="action", required=True)
    datasets_sub.add_parser("list")
    show_parser = datasets_sub.add_parser("show")
    show_parser.add_argument("id", type=int)
    export_parser = datasets_sub.add_parser("export")
    export_parser.add_argument("id", type=int)
    export_parser.add_argument("--kind", choices=["snapshot", "review"], required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    predict_parser = sub.add_parser("predict", help="Save exploratory prediction")
    predict_parser.add_argument("smiles")
    predict_parser.add_argument("--experiment-id", type=int)
    doctor_parser = sub.add_parser("doctor", help="Read-only configuration, database and server checks")
    start_parser = sub.add_parser("start", help="Run both local servers; Ctrl+C stops both")
    for local in (doctor_parser, start_parser):
        local.add_argument("--api-port", type=int, default=8000)
        local.add_argument("--dashboard-port", type=int, default=8501)
    backup_parser = sub.add_parser("backup", help="Checksummed workspace backup and recovery")
    backup_sub = backup_parser.add_subparsers(dest="action", required=True)
    create = backup_sub.add_parser("create")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--services-stopped", action="store_true")
    for action in ("inspect", "verify", "restore"):
        backup_action = backup_sub.add_parser(action)
        backup_action.add_argument("archive", type=Path)
        if action == "restore":
            backup_action.add_argument("--destination", type=Path, required=True)
            backup_action.add_argument("--database-url")
            backup_action.add_argument("--replace", action="store_true")
            backup_action.add_argument("--services-stopped", action="store_true")
    args = parser.parse_args()
    if args.command in {"doctor", "start", "backup"}:
        from cvti.config import get_settings
        try:
            settings = get_settings()
            if args.command == "doctor":
                from cvti.doctor import diagnose
                result = diagnose(settings, api_port=args.api_port, dashboard_port=args.dashboard_port)
                print(json.dumps(result, indent=2))
                return
            if args.command == "start":
                from cvti.launch import start
                start(args.api_port, args.dashboard_port)
                return
            from cvti.backup import create_backup, inspect_backup, restore_backup
            if args.action == "create":
                result = create_backup(settings.database_url, settings.artifact_dir, args.output,
                                       services_stopped=args.services_stopped)
            elif args.action == "restore":
                result = restore_backup(args.archive, args.destination, database_url=args.database_url,
                                        replace=args.replace, services_stopped=args.services_stopped)
            else:
                result = inspect_backup(args.archive)
            print(json.dumps(result, indent=2))
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"Unable to complete {args.command}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        return
    if args.command == "chembl" and args.action == "snapshot":
        try:
            print(json.dumps(fetch_snapshot(args.output), indent=2))
        except (SourceUnavailable, ValueError, OSError) as exc:
            print(f"Unable to save snapshot: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        return
    if args.command == "chembl" and args.action == "review-sheet":
        try:
            print(json.dumps(write_review_sheet(args.snapshot, args.output), indent=2))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"Unable to create review sheet: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        return
    from cvti.config import get_settings
    from cvti.workspace_lock import workspace_lock
    settings = get_settings()
    engine = make_engine()
    lock = workspace_lock(settings.database_url, settings.artifact_dir)
    acquired = False
    try:
        lock.__enter__()
        acquired = True
        init_db(engine)
        if args.command == "db":
            with engine.connect() as connection:
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            print(json.dumps({"database": "ready", "revision": revision}, indent=2))
            return
        with session_factory(engine)() as session:
            if args.command == "ingest":
                result = ingest_fixture(session) if args.source == "fixture" else ingest_live(session)
            elif args.command == "chembl":
                result = curate_snapshot(session, args.snapshot, args.review)
            elif args.command == "datasets":
                if args.action == "list":
                    versions = session.scalars(select(DatasetVersion).order_by(DatasetVersion.id.desc())).all()
                    result = [version_summary(version) for version in versions]
                else:
                    version = session.get(DatasetVersion, args.id)
                    if version is None:
                        raise ValueError(f"Dataset version {args.id} does not exist")
                    verify_version(version)
                    if args.action == "show":
                        result = {**version_summary(version), "policy": version.policy_json}
                    else:
                        content = version.snapshot_blob if args.kind == "snapshot" else version.review_blob
                        if content is None:
                            raise ValueError(f"Dataset version {args.id} has no {args.kind} file")
                        args.output.parent.mkdir(parents=True, exist_ok=True)
                        with args.output.open("xb") as output:
                            output.write(content)
                        result = {"dataset_version_id": version.id, "kind": args.kind,
                                  "output": str(args.output)}
            elif args.command == "train":
                run = train(session, args.source, dataset_version_id=args.dataset_version_id)
                result = {"experiment_id": run.id, "dataset_version_id": run.dataset_version_id,
                          "source": run.data_source, "metrics": run.metrics}
            else:
                result = predict(session, args.smiles, args.experiment_id)
    except (SourceUnavailable, ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"Unable to complete {args.command}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    finally:
        engine.dispose()
        if acquired:
            lock.__exit__(None, None, None)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
