import argparse
import json
import sys

from cvti.db import init_db, make_engine, session_factory
from cvti.ingest import SourceUnavailable, ingest_fixture, ingest_live
from cvti.ml import predict, train


def main():
    parser = argparse.ArgumentParser(description="PCSK9 research MVP")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_parser = sub.add_parser("ingest", help="Load synthetic fixture or live public data")
    ingest_parser.add_argument("--source", choices=["fixture", "live"], default="fixture")
    train_parser = sub.add_parser("train", help="Train scaffold-split IC50 baseline")
    train_parser.add_argument("--source", choices=["synthetic_fixture", "chembl"], default="synthetic_fixture")
    predict_parser = sub.add_parser("predict", help="Save exploratory prediction")
    predict_parser.add_argument("smiles")
    predict_parser.add_argument("--experiment-id", type=int)
    args = parser.parse_args()
    engine = make_engine()
    init_db(engine)
    try:
        with session_factory(engine)() as session:
            if args.command == "ingest":
                result = ingest_fixture(session) if args.source == "fixture" else ingest_live(session)
            elif args.command == "train":
                run = train(session, args.source)
                result = {"experiment_id": run.id, "source": run.data_source, "metrics": run.metrics}
            else:
                result = predict(session, args.smiles, args.experiment_id)
    except (SourceUnavailable, ValueError) as exc:
        print(f"Unable to complete {args.command}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
