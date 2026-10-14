import argparse
import json
import sys
from pathlib import Path
from sqlalchemy import text

from cvti.curation import curate_snapshot, fetch_snapshot, write_review_sheet
from cvti.db import init_db, make_engine, session_factory
from cvti.ingest import SourceUnavailable, ingest_fixture, ingest_live
from cvti.ml import predict, train


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
    predict_parser = sub.add_parser("predict", help="Save exploratory prediction")
    predict_parser.add_argument("smiles")
    predict_parser.add_argument("--experiment-id", type=int)
    args = parser.parse_args()
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
    engine = make_engine()
    try:
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
            elif args.command == "train":
                run = train(session, args.source)
                result = {"experiment_id": run.id, "source": run.data_source, "metrics": run.metrics}
            else:
                result = predict(session, args.smiles, args.experiment_id)
    except (SourceUnavailable, ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"Unable to complete {args.command}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
