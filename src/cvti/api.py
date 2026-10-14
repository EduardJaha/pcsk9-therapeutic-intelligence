from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from cvti.db import init_db, make_engine, session_factory
from cvti.ingest import ingest_fixture
from cvti.ml import predict, train
from cvti.models import Experiment, Measurement, Prediction, TargetEvidence


class PredictRequest(BaseModel):
    smiles: str = Field(min_length=1, max_length=1000)
    experiment_id: int | None = None


class TrainRequest(BaseModel):
    source: str = Field(default="synthetic_fixture", pattern="^(synthetic_fixture|chembl)$")


def create_app(database_url: str | None = None, artifact_dir: str | None = None) -> FastAPI:
    engine = make_engine(database_url)
    factory = session_factory(engine)

    @asynccontextmanager
    async def lifespan(app):
        init_db(engine)
        yield
        engine.dispose()

    app = FastAPI(title="PCSK9 Research Intelligence MVP", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health():
        with factory() as session:
            session.execute(select(1)).scalar_one()
        return {"status": "ok", "scope": "research-only"}

    @app.get("/summary")
    def summary():
        with factory() as session:
            return {"target": "PCSK9", "chembl_target_id": "CHEMBL2929",
                    "ensembl_id": "ENSG00000169174",
                    "measurements": session.scalar(select(func.count()).select_from(Measurement)),
                    "evidence_rows": session.scalar(select(func.count()).select_from(TargetEvidence)),
                    "experiments": session.scalar(select(func.count()).select_from(Experiment)),
                    "predictions": session.scalar(select(func.count()).select_from(Prediction))}

    @app.post("/fixtures/load")
    def load_fixtures():
        with factory() as session:
            return ingest_fixture(session)

    @app.post("/experiments")
    def create_experiment(request: TrainRequest):
        with factory() as session:
            try:
                run = train(session, request.source, artifact_dir)
                return {"id": run.id, "data_source": run.data_source, "metrics": run.metrics,
                        "n_molecules": run.n_molecules, "dataset_hash": run.dataset_hash}
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    @app.get("/experiments")
    def list_experiments():
        with factory() as session:
            runs = session.scalars(select(Experiment).order_by(Experiment.id.desc()).limit(50)).all()
            return [{"id": r.id, "created_at": r.created_at.isoformat(), "data_source": r.data_source,
                     "metrics": r.metrics, "n_molecules": r.n_molecules,
                     "n_scaffolds": r.n_scaffolds, "dataset_hash": r.dataset_hash} for r in runs]

    @app.get("/measurements")
    def list_measurements(limit: int = 100):
        with factory() as session:
            rows = session.scalars(select(Measurement).order_by(Measurement.id.desc()).limit(min(max(limit, 1), 500))).all()
            return [{"source": r.source, "activity_id": r.source_record_id, "molecule_id": r.molecule_id,
                     "canonical_smiles": r.canonical_smiles, "scaffold": r.scaffold,
                     "pchembl_value": r.pchembl_value, "activity_type": r.activity_type,
                     "source_url": r.source_url} for r in rows]

    @app.get("/evidence")
    def list_evidence():
        with factory() as session:
            rows = session.scalars(select(TargetEvidence).order_by(TargetEvidence.association_score.desc()).limit(50)).all()
            return [{"disease_id": r.disease_id, "disease_name": r.disease_name,
                     "association_score": r.association_score, "source_url": r.source_url} for r in rows]

    @app.post("/predict")
    def create_prediction(request: PredictRequest):
        with factory() as session:
            try:
                return predict(session, request.smiles, request.experiment_id)
            except (ValueError, FileNotFoundError) as exc:
                raise HTTPException(422, str(exc)) from exc

    return app


app = create_app()
