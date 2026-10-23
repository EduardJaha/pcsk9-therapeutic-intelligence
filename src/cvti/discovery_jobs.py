"""Durable scientific runs; completed records have no update/delete interface."""
import math
import hashlib
from pathlib import Path
from sqlalchemy import select, update

from cvti.discovery_chemistry import molecule
from cvti.discovery_models import ENDPOINTS, interpret_admet, run_engine
from cvti.models import DiscoveryModel, DiscoveryRun, utcnow
from cvti.registry import json_hash, project_exists


def engine_contract():
    return {name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('discovery_runtime.py','discovery_models.py','docking.py')}


def verify_run(run):
    if run.input_sha256 != json_hash(run.input_json):
        raise ValueError('Scientific run input checksum failed')
    if run.result_json is not None and run.result_sha256 != json_hash(run.result_json):
        raise ValueError('Scientific run result checksum failed')


def summary(run, details=False):
    verify_run(run)
    result = {k: getattr(run,k) for k in ('id','project_id','model_id','kind','status','input_sha256','result_sha256','error')}
    result.update(created_at=run.created_at.isoformat(), updated_at=run.updated_at.isoformat())
    if details:
        result.update(inputs=run.input_json, result=run.result_json)
    return result


def create_run(session, project_id, kind, inputs, result=None, model_id=None):
    project_exists(session, project_id)
    run = DiscoveryRun(project_id=project_id, model_id=model_id, kind=kind,
                       input_json=inputs, input_sha256=json_hash(inputs), result_json=result,
                       result_sha256=json_hash(result) if result is not None else None,
                       status='completed' if result is not None else 'queued')
    session.add(run)
    session.commit()
    return run


def validate_job(session, kind, payload):
    if kind == 'admet':
        model = session.get(DiscoveryModel, payload['model_id'])
        if model is None or model.manifest_sha256 != json_hash(model.manifest_json):
            raise ValueError('Model release is missing or failed its manifest checksum')
        ids = {e['id'] for e in ENDPOINTS}
        if not set(payload['endpoints']) <= ids or len(set(payload['endpoints'])) != len(payload['endpoints']):
            raise ValueError('Select distinct supported endpoints')
        canonical = [molecule(s)[0]['canonical_smiles'] for s in payload['smiles']]
        if len(set(canonical)) != len(canonical):
            raise ValueError('Use distinct standardized molecules in an ADMET batch')
        return {**payload, 'canonical_smiles': canonical, 'model_manifest_sha256': model.manifest_sha256,
                'engine_contract':engine_contract()}
    record, _ = molecule(payload['smiles'])
    atoms = [line for line in payload['receptor_pdbqt'].splitlines() if line.startswith(('ATOM  ', 'HETATM'))]
    if not atoms or len(atoms) > 30000:
        raise ValueError('Supply a prepared receptor PDBQT with 1–30,000 atoms')
    if any(line.startswith(('ROOT','BRANCH','MODEL')) for line in payload['receptor_pdbqt'].splitlines()):
        raise ValueError('Supply one rigid receptor, not ligand torsions or multiple models')
    try:
        coordinates = [[float(line[30:38]), float(line[38:46]), float(line[46:54])] for line in atoms]
        if not all(math.isfinite(v) for row in coordinates for v in row):
            raise ValueError()
    except (ValueError, IndexError) as exc:
        raise ValueError('Receptor atom coordinates are invalid') from exc
    if not any(all(abs(a-c) <= b/2 for a,c,b in zip(row,payload['center'],payload['box_size'])) for row in coordinates):
        raise ValueError('Docking box contains no receptor atoms; check the grid coordinates')
    return {**payload, 'canonical_smiles': record['canonical_smiles'],'engine_contract':engine_contract()}


def recover_jobs(factory):
    with factory() as session:
        session.execute(update(DiscoveryRun).where(DiscoveryRun.status == 'running').values(
            status='interrupted', error='Worker stopped; original inputs retained. Submit an explicit retry.', updated_at=utcnow()))
        session.commit()


def process_next(factory):
    with factory() as session:
        run = session.scalar(select(DiscoveryRun).where(DiscoveryRun.status=='queued').order_by(DiscoveryRun.id))
        if run is None:
            return None
        claimed = session.execute(update(DiscoveryRun).where(DiscoveryRun.id==run.id, DiscoveryRun.status=='queued').values(status='running', updated_at=utcnow())).rowcount
        session.commit()
        if not claimed:
            return None
        try:
            verify_run(run)
            payload = run.input_json
            if payload.get('engine_contract') != engine_contract():
                raise ValueError('Scientific implementation changed since submission; create a new job with the current version')
            if run.kind == 'admet':
                model = session.get(DiscoveryModel, run.model_id)
                if model is None or model.manifest_sha256 != json_hash(model.manifest_json) or model.manifest_sha256 != payload['model_manifest_sha256']:
                    raise ValueError('Model manifest checksum failed')
                raw = run_engine('admet', {'manifest': model.manifest_json, 'smiles': payload['canonical_smiles']})
                result = interpret_admet(raw, payload['canonical_smiles'], payload['endpoints'])
                result.update(model_manifest_sha256=model.manifest_sha256, model_manifest=model.manifest_json)
            elif run.kind == 'docking':
                from cvti.docking import run_docking
                result = run_docking(payload)
                if not result.get('poses_pdbqt') or not result.get('energies_kcal_mol'):
                    raise ValueError('Docking produced no poses')
            else:
                raise ValueError('Unknown job type')
            result['engine_contract'] = payload['engine_contract']
            run.result_sha256 = json_hash(result)
            run.result_json, run.status = result, 'completed'
        except Exception as exc:
            session.rollback()
            run = session.get(DiscoveryRun, run.id)
            run.status = 'failed'
            run.error = str(exc) if isinstance(exc, ValueError) else 'Scientific engine failed; no result accepted. Check runtime setup and submit a new run.'
        run.updated_at = utcnow()
        session.commit()
        return run.id
