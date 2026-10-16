"""Local project, collection, history and durable batch interfaces."""
import io
import json
import zipfile

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cvti.batches import csv_export, job_summary, retry_batch, submit_batch
from cvti.chemistry import standardize
from cvti.models import BatchJob, Collection, CollectionMolecule, DatasetVersion, Experiment, Prediction, Project


class NamedRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str = Field(default='', max_length=4000)


class CollectionRequest(NamedRequest):
    project_id: int = Field(default=1, gt=0)


class CollectionEntry(BaseModel):
    smiles: str = Field(min_length=1, max_length=1000)
    notes: str = Field(default='', max_length=4000)


class BatchRequest(BaseModel):
    csv_content: str = Field(min_length=1, max_length=2_000_000)
    smiles_column: str = Field(min_length=1, max_length=200)
    project_id: int = Field(default=1, gt=0)
    experiment_id: int | None = Field(default=None, gt=0)
    save_predictions: bool = False


def _prediction(row, run):
    return {'id': row.id, 'project_id': row.project_id, 'experiment_id': row.experiment_id,
            'dataset_version_id': run.dataset_version_id, 'created_at': row.created_at.isoformat(),
            'input_smiles': row.input_smiles, 'canonical_smiles': row.canonical_smiles,
            'exploratory_score': row.probability, 'source': run.data_source, 'research_notice': row.label}


def router(factory, artifact_dir):
    api = APIRouter()

    @api.get('/projects')
    def projects():
        with factory() as session:
            return [{'id': p.id, 'name': p.name, 'notes': p.notes} for p in session.scalars(select(Project).order_by(Project.id))]

    @api.post('/projects')
    def create_project(request: NamedRequest):
        if not request.name.strip():
            raise HTTPException(422, 'Project name cannot be blank')
        with factory() as session:
            project = Project(name=request.name.strip(), notes=request.notes)
            session.add(project)
            session.commit()
            return {'id': project.id, 'name': project.name, 'notes': project.notes}

    @api.patch('/projects/{project_id}')
    def update_project(project_id: int, request: NamedRequest):
        if not request.name.strip():
            raise HTTPException(422, 'Project name cannot be blank')
        with factory() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise HTTPException(404, 'Project not found')
            project.name, project.notes = request.name.strip(), request.notes
            session.commit()
            return {'id': project.id, 'name': project.name, 'notes': project.notes}

    @api.get('/collections')
    def collections(project_id: int = 1):
        with factory() as session:
            return [{'id': c.id, 'name': c.name, 'notes': c.notes, 'project_id': c.project_id}
                    for c in session.scalars(select(Collection).where(Collection.project_id == project_id).order_by(Collection.id))]

    @api.post('/collections')
    def create_collection(request: CollectionRequest):
        with factory() as session:
            if session.get(Project, request.project_id) is None:
                raise HTTPException(404, 'Project not found')
            if not request.name.strip():
                raise HTTPException(422, 'Collection name cannot be blank')
            collection = Collection(project_id=request.project_id, name=request.name.strip(), notes=request.notes)
            session.add(collection)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise HTTPException(409, 'A collection with this name already exists in the project') from exc
            return {'id': collection.id, 'name': collection.name, 'project_id': collection.project_id}

    @api.get('/collections/{collection_id}/molecules')
    def collection_entries(collection_id: int):
        with factory() as session:
            if session.get(Collection, collection_id) is None:
                raise HTTPException(404, 'Collection not found')
            return [{'id': r.id, 'input_smiles': r.input_smiles, 'canonical_smiles': r.canonical_smiles, 'notes': r.notes}
                    for r in session.scalars(select(CollectionMolecule).where(CollectionMolecule.collection_id == collection_id))]

    @api.post('/collections/{collection_id}/molecules')
    def add_entry(collection_id: int, request: CollectionEntry):
        with factory() as session:
            if session.get(Collection, collection_id) is None:
                raise HTTPException(404, 'Collection not found')
            try:
                canonical, _ = standardize(request.smiles)
                entry = CollectionMolecule(collection_id=collection_id, input_smiles=request.smiles,
                                           canonical_smiles=canonical, notes=request.notes)
                session.add(entry)
                session.commit()
                return {'id': entry.id, 'canonical_smiles': canonical}
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            except IntegrityError as exc:
                session.rollback()
                raise HTTPException(409, 'This standardized molecule is already in the collection') from exc

    @api.get('/predictions')
    def prediction_history(project_id: int = 1, experiment_id: int | None = None,
                           offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), format: str = 'json'):
        query = select(Prediction, Experiment).join(Experiment).where(Prediction.project_id == project_id)
        if experiment_id is not None:
            query = query.where(Prediction.experiment_id == experiment_id)
        with factory() as session:
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = [_prediction(p, run) for p, run in session.execute(query.order_by(Prediction.id.desc()).offset(offset).limit(limit))]
            if format == 'csv':
                return Response(csv_export(rows), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="predictions.csv"'})
            if format != 'json':
                raise HTTPException(422, 'Use json or csv format')
            return {'total': total, 'offset': offset, 'limit': limit, 'items': rows}

    @api.post('/batch-jobs')
    def create_batch(request: BatchRequest):
        with factory() as session:
            try:
                job = submit_batch(session, request.csv_content, request.smiles_column, experiment_id=request.experiment_id,
                                   project_id=request.project_id, save=request.save_predictions)
                return job_summary(job)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    @api.get('/batch-jobs')
    def batches(project_id: int = 1):
        with factory() as session:
            return [job_summary(job) for job in session.scalars(select(BatchJob).where(BatchJob.project_id == project_id)
                                                               .order_by(BatchJob.id.desc()).limit(100))]

    @api.get('/batch-jobs/{job_id}')
    def get_batch(job_id: int, format: str = 'json'):
        with factory() as session:
            job = session.get(BatchJob, job_id)
            if job is None:
                raise HTTPException(404, 'Batch job not found')
            if format == 'csv':
                return Response(csv_export(job.result_rows), media_type='text/csv',
                                headers={'Content-Disposition': f'attachment; filename="batch-{job_id}.csv"'})
            return job_summary(job, include_rows=True)

    @api.post('/batch-jobs/{job_id}/retry')
    def retry(job_id: int):
        with factory() as session:
            try:
                return job_summary(retry_batch(session, job_id))
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    @api.get('/research-reports/{experiment_id}')
    def unified_report(experiment_id: int, project_id: int = 1, prediction_ids: list[int] = Query(default=[])):
        from cvti.audit import audit_dataset
        from cvti.evaluation import model_card, evaluation_records
        from cvti.reports import assay_reviews, experiment_report, render_assay_review_csv, render_experiment_report
        from cvti.provenance import digest
        with factory() as session:
            run = session.get(Experiment, experiment_id)
            if run is None:
                raise HTTPException(404, 'Experiment not found')
            version = session.get(DatasetVersion, run.dataset_version_id)
            selected = []
            for identifier in prediction_ids:
                record = session.get(Prediction, identifier)
                if record is None or record.experiment_id != experiment_id or record.project_id != project_id:
                    raise HTTPException(422, 'Every selected prediction must belong to this project and experiment')
                selected.append(_prediction(record, run))
            evaluations = evaluation_records(session, run.id)
            report = experiment_report(run, version, evaluations)
            files = {'experiment.md': render_experiment_report(report), 'experiment.json': json.dumps(report, indent=2),
                     'dataset-audit.json': json.dumps(audit_dataset(version), indent=2),
                     'model-card.json': json.dumps(model_card(run, version, evaluations), indent=2),
                     'assay-review.csv': render_assay_review_csv(assay_reviews(version)),
                     'selected-predictions.csv': csv_export(selected)}
            project = session.get(Project, project_id)
            files['project.json'] = json.dumps({'id': project_id, 'name': project.name if project else None,
                                                'notes': project.notes if project else None}, indent=2)
            files['manifest.json'] = json.dumps({'experiment_id': run.id, 'dataset_version_id': version.id,
                                                'project_id': project_id, 'prediction_ids': prediction_ids,
                                                'files_sha256': {name: digest(content.encode()) for name, content in files.items()}}, indent=2)
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as bundle:
                for name, content in files.items():
                    bundle.writestr(name, content)
            return Response(output.getvalue(), media_type='application/zip',
                            headers={'Content-Disposition': f'attachment; filename="research-{experiment_id}.zip"'})
    return api
