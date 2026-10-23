"""Research tools, explicit persistence and local scientific jobs."""
from pathlib import Path
import hashlib
from importlib.metadata import version
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field, ValidationError
from sqlalchemy import select

from cvti import assay_analysis, discovery_chemistry as chemistry
from cvti.config import get_settings
from cvti.discovery_jobs import create_run, summary, validate_job
from cvti.discovery_models import ENDPOINTS, load_manifest
from cvti.discovery_schemas import ADMET, ANALYSES, Docking, Strict
from cvti.models import (AssayProtocol, AssayRun, CompoundBatch, DiscoveryModel, DiscoveryRun,
                         MaterialSample, RegisteredCompound)
from cvti.registry import json_hash, project_exists
from cvti.target_biology import target_dossier


class AnalysisRequest(Strict):
    project_id: int = Field(default=1, gt=0)
    kind: Literal['dossier','conformer','screen','sar','analogs','curve','plate','target']
    payload: dict
    save: bool = False


class JobRequest(Strict):
    project_id: int = Field(default=1, gt=0)
    kind: Literal['admet','docking']
    payload: dict


def analysis(kind, p):
    if kind == 'dossier': return chemistry.dossier(p['smiles'])
    if kind == 'conformer': return chemistry.conformer(p['smiles'])
    if kind == 'screen': return chemistry.screen(p['query'],p['smiles'],p['min_similarity'])
    if kind == 'sar': return chemistry.sar(p['csv_content'],p['similarity_threshold'])
    if kind == 'analogs': return chemistry.analogs(p['smiles'],p['transformations'])
    if kind == 'curve': return assay_analysis.fit_curve(p['concentrations'],p['responses'],p['units'],p['direction'])
    if kind == 'plate': return assay_analysis.plate_qc(p['positive'],p['negative'])
    if kind == 'target': return target_dossier(p['ensembl_id'],p['pdb_id'])
    raise ValueError('Unknown analysis')


def validate_curve_context(session, project_id, p):
    if p['assay_run_id'] is None:
        return {'linked_to_assay': False, 'data_origin': p['data_origin'], 'source_reference': p['source_reference']}
    run = session.get(AssayRun,p['assay_run_id'])
    sample = session.get(MaterialSample,p['sample_id'])
    protocol = session.get(AssayProtocol,run.protocol_id) if run else None
    batch = session.get(CompoundBatch,sample.batch_id) if sample else None
    compound = session.get(RegisteredCompound,batch.compound_id) if batch else None
    if not protocol or not compound or protocol.project_id != project_id or compound.project_id != project_id:
        raise ValueError('Assay run and sample must belong to this project')
    if run.data_origin != p['data_origin'] or batch.data_origin != p['data_origin'] or compound.modality != protocol.modality:
        raise ValueError('Curve origin/modality does not match the assay and material')
    return {'linked_to_assay': True, 'assay_run_id':run.id,'sample_id':sample.id,'compound_id':compound.id,
            'protocol_id':protocol.id,'target':protocol.target_id,'endpoint':protocol.endpoint,
            'activity_type':protocol.activity_type,'modality':protocol.modality,'data_origin':run.data_origin,
            'source_reference':p['source_reference'], 'status':'unreviewed analysis; no observation or training record created'}


def router(factory):
    api = APIRouter(prefix='/discovery', tags=['Discovery workbench'])

    @api.get('/capabilities')
    def capabilities():
        settings = get_settings()
        return {'local_chemistry': True, 'curve_analysis': True, 'sar': True,
                'optional_python_present': Path(settings.discovery_python).is_file(),
                'admet_manifest_present': Path(settings.admet_manifest).is_file(),
                'vina_present': Path(settings.vina_executable).is_file(),
                'notice': 'File presence is not a runtime or scientific validation. Inference is local; target retrieval uses explicitly supplied public identifiers.'}

    @api.get('/endpoints')
    def endpoints():
        return ENDPOINTS

    @api.get('/models')
    def models():
        with factory() as session:
            return [{'id':m.id,'manifest_sha256':m.manifest_sha256,'manifest':m.manifest_json}
                    for m in session.scalars(select(DiscoveryModel).order_by(DiscoveryModel.id.desc()))]

    @api.post('/models/register-local')
    def register_model():
        try:
            manifest = load_manifest()
            checksum = json_hash(manifest)
            with factory() as session:
                model = session.scalar(select(DiscoveryModel).where(DiscoveryModel.manifest_sha256==checksum))
                if model is None:
                    model = DiscoveryModel(manifest_sha256=checksum,manifest_json=manifest)
                    session.add(model)
                    session.commit()
                return {'id':model.id,'manifest_sha256':checksum,'manifest':manifest}
        except (ValueError, OSError) as exc:
            raise HTTPException(422,str(exc)) from exc

    @api.post('/analyze')
    def analyze(request: AnalysisRequest):
        try:
            payload = ANALYSES[request.kind].model_validate(request.payload).model_dump()
            with factory() as session:
                project_exists(session,request.project_id)
                context = validate_curve_context(session,request.project_id,payload) if request.kind=='curve' else None
                result = analysis(request.kind,payload)
                result['implementation'] = {
                    'policy': 'discovery-v1', 'rdkit': version('rdkit'), 'scipy': version('scipy'),
                    'source_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                      for name in ('discovery_chemistry.py','assay_analysis.py','target_biology.py')}}
                if context: result['assay_context'] = context
                run = create_run(session,request.project_id,request.kind,payload,result) if request.save else None
                return {'run_id':run.id if run else None,'kind':request.kind,'result':result,
                        'input_sha256':json_hash(payload),'result_sha256':json_hash(result)}
        except LookupError as exc:
            raise HTTPException(404,str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422,str(exc)) from exc

    @api.post('/jobs')
    def submit(request: JobRequest):
        try:
            payload = (ADMET if request.kind=='admet' else Docking).model_validate(request.payload).model_dump()
            with factory() as session:
                project_exists(session,request.project_id)
                payload = validate_job(session,request.kind,payload)
                return summary(create_run(session,request.project_id,request.kind,payload,
                                          model_id=payload.get('model_id')),True)
        except LookupError as exc:
            raise HTTPException(404,str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc

    @api.get('/runs')
    def runs(project_id: int = Query(1,gt=0), limit: int = Query(100,ge=1,le=500)):
        with factory() as session:
            try:
                project_exists(session,project_id)
                return [summary(r) for r in session.scalars(select(DiscoveryRun).where(DiscoveryRun.project_id==project_id)
                                                           .order_by(DiscoveryRun.id.desc()).limit(limit))]
            except LookupError as exc: raise HTTPException(404,str(exc)) from exc
            except ValueError as exc: raise HTTPException(409,str(exc)) from exc

    @api.get('/runs/{identifier}')
    def run(identifier: int, project_id: int = Query(1,gt=0)):
        with factory() as session:
            record = session.get(DiscoveryRun,identifier)
            if record is None or record.project_id != project_id:
                raise HTTPException(404,'Research run not found in this project')
            try: return summary(record,True)
            except ValueError as exc: raise HTTPException(409,str(exc)) from exc

    @api.post('/runs/{identifier}/retry')
    def retry(identifier: int, project_id: int = Query(1,gt=0)):
        with factory() as session:
            record = session.get(DiscoveryRun,identifier)
            if record is None or record.project_id != project_id:
                raise HTTPException(404,'Research run not found in this project')
            if record.status not in {'failed','interrupted'} or record.kind not in {'admet','docking'}:
                raise HTTPException(409,'Only failed or interrupted scientific jobs can be retried')
            try:
                summary(record)
                inputs = {**record.input_json,'retry_of':record.id}
                return summary(create_run(session,project_id,record.kind,inputs,model_id=record.model_id),True)
            except ValueError as exc: raise HTTPException(409,str(exc)) from exc

    return api
