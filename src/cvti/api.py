from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from cvti.db import init_db, make_engine, session_factory, prepare_database
from cvti.ingest import ingest_fixture
from cvti.ml import predict, train
from cvti.models import DatasetVersion, Experiment, Measurement, Prediction, TargetEvidence
from cvti.provenance import verify_version, version_summary
from cvti.reports import assay_reviews, experiment_report, render_experiment_report
from cvti.config import get_settings
from cvti.workspace_lock import workspace_lock
from cvti.workbench import chemical_space, molecule_profile


class PredictRequest(BaseModel):
    project_id: int = Field(default=1, gt=0)
    smiles: str = Field(min_length=1, max_length=1000)
    experiment_id: int | None = Field(default=None, gt=0)
    save: bool = True


class MoleculeRequest(BaseModel):
    smiles: str = Field(min_length=1, max_length=1000)


class CompareRequest(BaseModel):
    smiles: list[str] = Field(min_length=2, max_length=6)
    experiment_id: int | None = Field(default=None, gt=0)


class ReviewSubmission(BaseModel):
    csv_content: str = Field(min_length=1, max_length=2_000_000)


class TrainRequest(BaseModel):
    project_id: int = Field(default=1, gt=0)
    model_kind: Literal["random_forest", "logistic_regression", "dummy"] = "random_forest"
    protocol_id: int | None = Field(default=None, gt=0)
    source: str = Field(default="synthetic_fixture", pattern="^(synthetic_fixture|chembl_curated)$")
    dataset_version_id: int | None = Field(default=None, gt=0)


def create_app(database_url: str | None = None, artifact_dir: str | None = None) -> FastAPI:
    engine = make_engine(database_url)
    factory = session_factory(engine)

    @asynccontextmanager
    async def lifespan(app):
        prepare_database(engine, str(engine.url), artifact_dir or get_settings().artifact_dir)
        with workspace_lock(str(engine.url), artifact_dir or get_settings().artifact_dir, shared=True):
            try:
                yield
            finally:
                engine.dispose()

    app = FastAPI(title="PCSK9 Research Intelligence MVP", version="0.2.0", lifespan=lifespan)

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
                run = train(session, request.source, artifact_dir, request.dataset_version_id,
                            protocol_id=request.protocol_id, model_kind=request.model_kind, project_id=request.project_id)
                return {"id": run.id, "data_source": run.data_source, "metrics": run.metrics,
                        "n_molecules": run.n_molecules, "dataset_hash": run.dataset_hash,
                        "dataset_version_id": run.dataset_version_id}
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    @app.get("/experiments")
    def list_experiments():
        with factory() as session:
            runs = session.scalars(select(Experiment).order_by(Experiment.id.desc()).limit(50)).all()
            return [{"id": r.id, "created_at": r.created_at.isoformat(), "data_source": r.data_source,
                     "metrics": r.metrics, "n_molecules": r.n_molecules,
                     "n_scaffolds": r.n_scaffolds, "dataset_hash": r.dataset_hash,
                     "dataset_version_id": r.dataset_version_id, "project_id": r.project_id, "model_kind": r.model_kind, "protocol_id": r.protocol_id,
                     "artifact_sha256": r.artifact_sha256, "provenance": r.provenance_json} for r in runs]

    @app.get("/dataset-versions")
    def list_dataset_versions():
        with factory() as session:
            versions = session.scalars(select(DatasetVersion).order_by(DatasetVersion.id.desc()).limit(100)).all()
            return [version_summary(version) for version in versions]

    @app.get("/dataset-versions/{version_id}")
    def get_dataset_version(version_id: int):
        with factory() as session:
            version = session.get(DatasetVersion, version_id)
            if version is None:
                raise HTTPException(404, "Dataset version not found")
            try:
                verify_version(version)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            return {**version_summary(version), "policy": version.policy_json}

    @app.get("/dataset-versions/{version_id}/assays")
    def get_assay_reviews(version_id: int):
        with factory() as session:
            version = session.get(DatasetVersion, version_id)
            if version is None:
                raise HTTPException(404, "Dataset version not found")
            try:
                return {"dataset_version_id": version.id, "status": version.status,
                        "assays": assay_reviews(version)}
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get('/dataset-versions/{version_id}/audit')
    def get_dataset_audit(version_id: int):
        from cvti.audit import audit_dataset
        with factory() as session:
            version = session.get(DatasetVersion, version_id)
            if version is None:
                raise HTTPException(404, 'Dataset version not found')
            try:
                return audit_dataset(version)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get('/dataset-versions/{version_id}/review-sheet')
    def get_review_sheet(version_id: int):
        import tempfile
        from pathlib import Path
        from cvti.curation import write_review_sheet
        with factory() as session:
            version = session.get(DatasetVersion, version_id)
            if version is None:
                raise HTTPException(404, 'Dataset version not found')
            verify_version(version)
            if version.source != 'chembl_curated' or not version.snapshot_blob:
                raise HTTPException(422, 'A stored ChEMBL snapshot is required')
            if version.review_blob:
                return {'csv_content': version.review_blob.decode('utf-8')}
            with tempfile.TemporaryDirectory() as folder:
                snapshot = Path(folder) / 'snapshot.json'
                output = Path(folder) / 'review.csv'
                snapshot.write_bytes(version.snapshot_blob)
                write_review_sheet(snapshot, output)
                return {'csv_content': output.read_text()}

    @app.post('/dataset-versions/{version_id}/reviews')
    def submit_review(version_id: int, request: ReviewSubmission):
        import tempfile
        from pathlib import Path
        from cvti.curation import curate_snapshot
        with factory() as session:
            version = session.get(DatasetVersion, version_id)
            if version is None:
                raise HTTPException(404, 'Dataset version not found')
            try:
                verify_version(version)
                if version.source != 'chembl_curated' or not version.snapshot_blob:
                    raise ValueError('A stored ChEMBL snapshot is required')
                with tempfile.TemporaryDirectory() as folder:
                    snapshot, review = Path(folder) / 'snapshot.json', Path(folder) / 'review.csv'
                    snapshot.write_bytes(version.snapshot_blob)
                    review.write_text(request.csv_content, encoding='utf-8')
                    return curate_snapshot(session, snapshot, review)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    @app.get("/experiments/{experiment_id}/report")
    def get_experiment_report(experiment_id: int, format: Literal["json", "markdown"] = "json"):
        with factory() as session:
            run = session.get(Experiment, experiment_id)
            if run is None:
                raise HTTPException(404, "Experiment not found")
            version = session.get(DatasetVersion, run.dataset_version_id)
            if version is None:
                raise HTTPException(409, "Experiment dataset version is missing")
            try:
                from cvti.evaluation import evaluation_records
                report = experiment_report(run, version, evaluation_records(session, run.id))
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            if format == "markdown":
                return Response(render_experiment_report(report), media_type="text/markdown",
                                headers={"Content-Disposition": f'attachment; filename="experiment-{run.id}.md"'})
            return report

    @app.get('/experiments/{experiment_id}/model-card')
    def get_model_card(experiment_id: int):
        from cvti.evaluation import model_card
        with factory() as session:
            run = session.get(Experiment, experiment_id)
            if run is None:
                raise HTTPException(404, 'Experiment not found')
            version = session.get(DatasetVersion, run.dataset_version_id)
            verify_version(version)
            from cvti.evaluation import evaluation_records
            return model_card(run, version, evaluation_records(session, run.id))

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
                return predict(session, request.smiles, request.experiment_id, save=request.save, project_id=request.project_id)
            except (ValueError, FileNotFoundError) as exc:
                raise HTTPException(422, str(exc)) from exc

    @app.post("/molecules/profile")
    def profile_molecule(request: MoleculeRequest):
        try:
            return molecule_profile(request.smiles)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/molecules/compare")
    def compare_molecules(request: CompareRequest):
        with factory() as session:
            try:
                if any(not isinstance(smiles, str) or not 1 <= len(smiles) <= 1000 for smiles in request.smiles):
                    raise ValueError("Each SMILES must contain 1 to 1000 characters")
                profiles = [molecule_profile(smiles) for smiles in request.smiles]
                space = chemical_space(profiles)
                for profile in profiles:
                    profile["prediction"] = (predict(session, profile["canonical_smiles"],
                                                      request.experiment_id, save=False)
                                             if request.experiment_id is not None else None)
                return {"molecules": profiles, "chemical_space": space,
                        "experiment_id": request.experiment_id, "predictions_saved": False}
            except (ValueError, FileNotFoundError) as exc:
                raise HTTPException(422, str(exc)) from exc

    from cvti.research_api import router as research_router
    app.include_router(research_router(factory, artifact_dir or get_settings().artifact_dir))
    from cvti.assistant_api import router as assistant_router
    app.include_router(assistant_router(factory))
    from cvti.registry_api import router as registry_router
    app.include_router(registry_router(factory))
    return app


app = create_app()
