"""Local registry interfaces with explicit writes and read-only candidate scoring."""
import io
import json
import zipfile
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cvti.batches import csv_export
from cvti.models import (AssayProtocol, AssayRun, CompoundBatch, DatasetVersion, Experiment,
                         MaterialSample, Project, RegisteredCompound, RegistrationImport, ResearchView)
from cvti.provenance import digest
from cvti.registry import (REGISTRY_NOTICE, RegistryConflict, batch_in_project, commit_registration,
                           compound_in_project, compound_summary, compound_svg, json_hash, observations,
                           preview_registration, project_exists, protocol_in_project, record_observation,
                           register_compound, run_in_project, search_registry, stage_summary)
from cvti.registry_schemas import (BatchInput, CommitInput, CompoundFilter, CompoundInput, ImportInput, Input,
                                   ObservationInput, ProtocolInput, RunInput, SampleInput, ScoreInput,
                                   ViewInput, WorkbenchInput)


def record_fields(record):
    result = {column.name: getattr(record, column.name) for column in record.__table__.columns}
    return {key: value.isoformat() if hasattr(value, 'isoformat') else value for key, value in result.items()}


@contextmanager
def database(factory, write=False, snapshot=False):
    with factory() as session:
        try:
            if snapshot:
                if session.get_bind().dialect.name == 'postgresql':
                    session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
                else:
                    # sqlite3's legacy mode does not start transactions for SELECT.
                    session.connection().exec_driver_sql('BEGIN')
            yield session
            if write:
                session.commit()
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except RegistryConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(409, 'A record with this identity already exists. Refresh and inspect the existing records.') from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


def material_records(session, project_id):
    batches = session.scalars(select(CompoundBatch).join(RegisteredCompound)
                               .where(RegisteredCompound.project_id == project_id).order_by(CompoundBatch.id)).all()
    samples = session.scalars(select(MaterialSample).join(CompoundBatch).join(RegisteredCompound)
                               .where(RegisteredCompound.project_id == project_id).order_by(MaterialSample.id)).all()
    return {'batches': [record_fields(row) for row in batches], 'samples': [record_fields(row) for row in samples]}


def router(factory):
    api = APIRouter(prefix='/registry', tags=['Local research registry'])

    @api.get('/compounds')
    def compounds(project_id: int = Query(1, gt=0), limit: int = Query(500, ge=1, le=1000),
                  offset: int = Query(0, ge=0)):
        from sqlalchemy import func
        with database(factory) as session:
            project_exists(session, project_id)
            query = select(RegisteredCompound).where(RegisteredCompound.project_id == project_id)
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(query.order_by(RegisteredCompound.id).offset(offset).limit(limit))
            return {'total': total, 'offset': offset, 'items': [compound_summary(row) for row in rows]}

    @api.post('/compounds')
    def register(request: CompoundInput):
        with database(factory, write=True) as session:
            record, created = register_compound(session, request)
            return {**compound_summary(record), 'created': created}

    @api.get('/compounds/{compound_id}')
    def compound_detail(compound_id: int, project_id: int = Query(1, gt=0)):
        with database(factory) as session:
            compound = compound_in_project(session, compound_id, project_id)
            materials = material_records(session, project_id)
            batches = [row for row in materials['batches'] if row['compound_id'] == compound_id]
            batch_ids = {row['id'] for row in batches}
            return {'compound': compound_summary(compound), 'svg': compound_svg(compound), 'batches': batches,
                    'samples': [row for row in materials['samples'] if row['batch_id'] in batch_ids],
                    'observations': observations(session, project_id, compound_id=compound_id), 'notice': REGISTRY_NOTICE}

    @api.get('/materials')
    def materials(project_id: int = Query(1, gt=0)):
        with database(factory) as session:
            project_exists(session, project_id)
            return material_records(session, project_id)

    @api.post('/batches')
    def add_batch(request: BatchInput):
        with database(factory, write=True) as session:
            compound_in_project(session, request.compound_id, request.project_id)
            record = CompoundBatch(**request.model_dump(exclude={'project_id'}))
            session.add(record)
            session.flush()
            return record_fields(record)

    @api.post('/samples')
    def add_sample(request: SampleInput):
        with database(factory, write=True) as session:
            batch_in_project(session, request.batch_id, request.project_id)
            record = MaterialSample(**request.model_dump(exclude={'project_id'}))
            session.add(record)
            session.flush()
            return record_fields(record)

    @api.get('/protocols')
    def protocols(project_id: int = Query(1, gt=0)):
        with database(factory) as session:
            project_exists(session, project_id)
            return [record_fields(row) for row in session.scalars(select(AssayProtocol)
                    .where(AssayProtocol.project_id == project_id).order_by(AssayProtocol.id))]

    @api.post('/protocols')
    def add_protocol(request: ProtocolInput):
        with database(factory, write=True) as session:
            project_exists(session, request.project_id)
            record = AssayProtocol(**request.model_dump(), target_id='CHEMBL2929')
            session.add(record)
            session.flush()
            return {**record_fields(record), 'review_status': 'recorded_unreviewed'}

    @api.get('/runs')
    def runs(project_id: int = Query(1, gt=0)):
        with database(factory) as session:
            project_exists(session, project_id)
            return [record_fields(row) for row in session.scalars(select(AssayRun).join(AssayProtocol)
                    .where(AssayProtocol.project_id == project_id).order_by(AssayRun.id))]

    @api.post('/runs')
    def add_run(request: RunInput):
        with database(factory, write=True) as session:
            protocol_in_project(session, request.protocol_id, request.project_id)
            record = AssayRun(**request.model_dump(exclude={'project_id'}))
            session.add(record)
            session.flush()
            return record_fields(record)

    @api.get('/observations')
    def assay_observations(project_id: int = Query(1, gt=0), run_id: int | None = Query(None, gt=0)):
        with database(factory) as session:
            project_exists(session, project_id)
            if run_id is not None:
                run_in_project(session, run_id, project_id)
            return {'items': observations(session, project_id, run_id=run_id), 'notice': REGISTRY_NOTICE}

    @api.post('/observations')
    def add_observation(request: ObservationInput):
        with database(factory, write=True) as session:
            record = record_observation(session, request)
            return {**record_fields(record), 'review_status': 'recorded_unreviewed', 'notice': REGISTRY_NOTICE}

    @api.post('/imports/preview')
    def import_preview(request: ImportInput):
        with database(factory, write=True) as session:
            return stage_summary(preview_registration(session, request))

    @api.get('/imports')
    def imports(project_id: int = Query(1, gt=0)):
        with database(factory) as session:
            project_exists(session, project_id)
            return [{'id': row.id, 'status': row.status, 'input_sha256': row.input_sha256,
                     'created_at': row.created_at.isoformat()}
                    for row in session.scalars(select(RegistrationImport).where(RegistrationImport.project_id == project_id)
                                               .order_by(RegistrationImport.id.desc()))]

    @api.get('/imports/{stage_id}')
    def get_import(stage_id: int, project_id: int = Query(1, gt=0)):
        with database(factory) as session:
            stage = session.get(RegistrationImport, stage_id)
            if stage is None or stage.project_id != project_id:
                raise LookupError('Registration preview not found in this project')
            return stage_summary(stage)

    @api.post('/imports/{stage_id}/commit')
    def import_commit(stage_id: int, request: CommitInput):
        with database(factory, write=True) as session:
            return stage_summary(commit_registration(session, stage_id, request.project_id, request.plan_sha256))

    @api.post('/workbench/search')
    def workbench(request: WorkbenchInput):
        with database(factory) as session:
            return search_registry(session, request.project_id, request.criteria)

    @api.get('/views')
    def views(project_id: int = Query(1, gt=0)):
        with database(factory) as session:
            project_exists(session, project_id)
            return [record_fields(row) for row in session.scalars(select(ResearchView)
                    .where(ResearchView.project_id == project_id).order_by(ResearchView.id))]

    @api.post('/views')
    def save_view(request: ViewInput):
        with database(factory, write=True) as session:
            project_exists(session, request.project_id)
            criteria = request.criteria.model_dump()
            record = ResearchView(project_id=request.project_id, name=request.name,
                                  criteria_json=criteria, criteria_sha256=json_hash(criteria))
            session.add(record)
            session.flush()
            return record_fields(record)

    @api.post('/views/{view_id}/run')
    def run_view(view_id: int, request: Input):
        with database(factory) as session:
            view = session.get(ResearchView, view_id)
            if view is None or view.project_id != request.project_id:
                raise LookupError('Saved view not found in this project')
            if view.criteria_sha256 != json_hash(view.criteria_json):
                raise RegistryConflict('Saved view integrity check failed')
            return search_registry(session, request.project_id, CompoundFilter(**view.criteria_json))

    @api.post('/workbench/score')
    def score_candidates(request: ScoreInput):
        from cvti.evaluation import evaluation_records, model_card
        from cvti.ml import predict
        with database(factory) as session:
            run = session.get(Experiment, request.experiment_id)
            if run is None or run.project_id != request.project_id:
                raise LookupError('Experiment not found in this project')
            compounds = [compound_in_project(session, identifier, request.project_id) for identifier in request.compound_ids]
            version = session.get(DatasetVersion, run.dataset_version_id)
            if version is None:
                raise RegistryConflict('Experiment dataset version is missing')
            items = []
            for compound in compounds:
                row = {'compound_id': compound.id, 'experiment_id': run.id, 'dataset_version_id': version.id}
                try:
                    if compound.modality != 'small_molecule':
                        raise ValueError('This scoring workflow supports small-molecule hypotheses only; no peptide model has been evaluated')
                    result = predict(session, compound.canonical_smiles, run.id, save=False, project_id=request.project_id)
                    row.update(status='ok', prediction=result)
                except (ValueError, FileNotFoundError) as exc:
                    row.update(status='error', message=str(exc))
                items.append(row)
            return {'project_id': request.project_id, 'experiment_id': run.id, 'dataset_version_id': version.id,
                    'model_card': model_card(run, version, evaluation_records(session, run.id)),
                    'items': items, 'predictions_saved': False}

    @api.get('/export')
    def export_registry(project_id: int = Query(1, gt=0)):
        with database(factory, snapshot=True) as session:
            project_exists(session, project_id)
            compounds = [compound_summary(row) for row in session.scalars(select(RegisteredCompound)
                         .where(RegisteredCompound.project_id == project_id).order_by(RegisteredCompound.id))]
            materials = material_records(session, project_id)
            protocols = [record_fields(row) for row in session.scalars(select(AssayProtocol).where(AssayProtocol.project_id == project_id))]
            runs = [record_fields(row) for row in session.scalars(select(AssayRun).join(AssayProtocol)
                    .where(AssayProtocol.project_id == project_id))]
            views = [record_fields(row) for row in session.scalars(select(ResearchView).where(ResearchView.project_id == project_id))]
            readouts = observations(session, project_id)
            files = {'compounds.json': json.dumps(compounds, indent=2), 'materials.json': json.dumps(materials, indent=2),
                     'protocols.json': json.dumps(protocols, indent=2), 'runs.json': json.dumps(runs, indent=2),
                     'observations.csv': csv_export(readouts),
                     'observations.json': json.dumps(readouts, indent=2),
                     'project.json': json.dumps(record_fields(session.get(Project, project_id)), indent=2),
                     'saved-views.json': json.dumps(views, indent=2),
                     'README.txt': REGISTRY_NOTICE + '\nOriginal units, inequality relations and sources are retained. No readouts are averaged.\n'}
            for stage in session.scalars(select(RegistrationImport).where(RegistrationImport.project_id == project_id)):
                files[f'imports/{stage.id}.csv'] = stage.csv_content
                files[f'imports/{stage.id}.json'] = json.dumps(stage_summary(stage), indent=2)
            files['manifest.json'] = json.dumps({'schema_version': 1, 'project_id': project_id,
                'files_sha256': {name: digest(content.encode()) for name, content in files.items()}}, indent=2)
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as bundle:
                for name, content in files.items():
                    bundle.writestr(name, content)
            return Response(output.getvalue(), media_type='application/zip',
                            headers={'Content-Disposition': f'attachment; filename="registry-project-{project_id}.zip"'})

    return api
