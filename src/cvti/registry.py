"""Compound identity, staged registration and material-linked research observations.

These records are deliberately outside the curated Measurement/DatasetVersion
training path. No operation in this module approves an assay or pools readouts.
"""
import csv
import io
import json
import math
from collections import Counter
from decimal import Decimal, InvalidOperation

from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem.MolStandardize import rdMolStandardize
from sqlalchemy import select

from cvti.chemistry import morgan_bits
from cvti.models import (AssayObservation, AssayProtocol, AssayRun, CompoundBatch,
                         MaterialSample, Project, RegisteredCompound, RegistrationImport)
from cvti.provenance import digest
from cvti.registry_schemas import CompoundInput, ImportInput

CHEMISTRY_POLICY = 'registry-charge-parent-v1'
REGISTRY_NOTICE = 'Calculated descriptors and recorded observations are research records. Assays remain unreviewed and are not included in model training.'


class RegistryConflict(ValueError):
    pass


def json_hash(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode())


def project_exists(session, project_id):
    if session.get(Project, project_id) is None:
        raise LookupError('Project not found')


def compound_in_project(session, compound_id, project_id):
    compound = session.get(RegisteredCompound, compound_id)
    if compound is None or compound.project_id != project_id:
        raise LookupError('Compound not found in this project')
    return compound


def structure_record(smiles):
    """Normalize registration identity without the training-only ring requirement."""
    if not isinstance(smiles, str) or not 1 <= len(smiles) <= 1000:
        raise ValueError('SMILES must contain 1 to 1,000 characters')
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or mol.GetNumHeavyAtoms() < 2:
        raise ValueError('Invalid or unsupported SMILES; at least two heavy atoms are required')
    warnings = []
    if len(Chem.GetMolFrags(mol)) > 1:
        warnings.append('Multiple input fragments: charge-parent normalization may remove salts or fragments. Original SMILES retained.')
    mol = rdMolStandardize.ChargeParent(mol)
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    if any(label == '?' for _, label in Chem.FindMolChiralCenters(mol, includeUnassigned=True)):
        warnings.append('Unspecified stereochemistry is present; this identity does not assert a specific stereoisomer.')
    props = {'molecular_weight': round(Descriptors.MolWt(mol), 2), 'logp': round(Descriptors.MolLogP(mol), 2),
             'tpsa': round(rdMolDescriptors.CalcTPSA(mol), 2), 'h_bond_donors': rdMolDescriptors.CalcNumHBD(mol),
             'h_bond_acceptors': rdMolDescriptors.CalcNumHBA(mol),
             'rotatable_bonds': rdMolDescriptors.CalcNumRotatableBonds(mol)}
    return {'canonical_smiles': canonical, 'structure_sha256': digest(canonical.encode()),
            'chemistry': {'policy': CHEMISTRY_POLICY, 'rdkit_version': rdBase.rdkitVersion,
                          'formula': rdMolDescriptors.CalcMolFormula(mol), 'properties': props, 'warnings': warnings}}


def register_compound(session, request: CompoundInput, normalized=None):
    project_exists(session, request.project_id)
    normalized = normalized or structure_record(request.smiles)
    existing = session.scalar(select(RegisteredCompound).where(
        RegisteredCompound.project_id == request.project_id,
        RegisteredCompound.structure_sha256 == normalized['structure_sha256']))
    if existing:
        if existing.canonical_smiles != normalized['canonical_smiles']:
            raise RegistryConflict('Structure identity hash collision; registration requires inspection')
        if existing.modality != request.modality:
            raise RegistryConflict('This structure is already registered with a different modality; inspect the existing record')
        return existing, False
    record = RegisteredCompound(project_id=request.project_id, name=request.name.strip(), input_smiles=request.smiles,
                                canonical_smiles=normalized['canonical_smiles'], structure_sha256=normalized['structure_sha256'],
                                modality=request.modality, source_reference=request.source_reference, notes=request.notes,
                                chemistry_json=normalized['chemistry'])
    session.add(record)
    session.flush()
    return record, True


def compound_summary(record):
    return {'id': record.id, 'code': f'CMP-{record.id:06d}', 'project_id': record.project_id,
            'name': record.name, 'input_smiles': record.input_smiles, 'canonical_smiles': record.canonical_smiles,
            'structure_sha256': record.structure_sha256, 'modality': record.modality,
            'source_reference': record.source_reference, 'notes': record.notes,
            'created_at': record.created_at.isoformat(), **record.chemistry_json}


def stage_summary(stage):
    return {'id': stage.id, 'project_id': stage.project_id, 'status': stage.status,
            'input_sha256': stage.input_sha256, 'plan_sha256': stage.plan_sha256,
            'settings': stage.settings_json, 'counts': dict(Counter(r['status'] for r in stage.rows_json)),
            'rows': stage.rows_json, 'outcome': stage.outcome_json}


def plan_hash(stage):
    return json_hash({'project_id': stage.project_id, 'input_sha256': stage.input_sha256,
                      'settings': stage.settings_json, 'rows': stage.rows_json})


def preview_registration(session, request: ImportInput):
    project_exists(session, request.project_id)
    reader = csv.DictReader(io.StringIO(request.csv_content.lstrip('\ufeff')), strict=True)
    try:
        fields = reader.fieldnames
    except csv.Error as exc:
        raise ValueError('Unable to read CSV header; check quoting') from exc
    selected = [value for value in [request.smiles_column, request.name_column, request.notes_column] if value is not None]
    if not fields or len(set(fields)) != len(fields) or any(value not in fields for value in selected):
        raise ValueError('Map existing, unambiguous CSV columns')
    rows, seen = [], {}
    try:
        for number, raw in enumerate(reader, 1):
            if number > 1000:
                raise ValueError('Registration import exceeds the 1,000-row limit')
            row = {'row': number, 'input': {key: value for key, value in raw.items() if key is not None}}
            if None in raw:
                row['extra_cells'] = raw[None]
            try:
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError('Column count differs from the CSV header')
                item = CompoundInput(project_id=request.project_id, smiles=raw[request.smiles_column].strip(),
                                     name=raw[request.name_column] if request.name_column else '',
                                     notes=raw[request.notes_column] if request.notes_column else '',
                                     modality=request.modality, source_reference=request.source_reference)
                structure = structure_record(item.smiles)
                row.update(registration=item.model_dump(), **structure)
                existing = session.scalar(select(RegisteredCompound).where(
                    RegisteredCompound.project_id == request.project_id,
                    RegisteredCompound.structure_sha256 == structure['structure_sha256']))
                if existing and existing.modality != request.modality:
                    raise ValueError('Structure is already registered with a different modality')
                key = structure['structure_sha256']
                if key in seen:
                    row.update(status='duplicate', duplicate_of_row=seen[key])
                elif existing:
                    row.update(status='existing', compound_id=existing.id)
                else:
                    row.update(status='ready')
                seen[key] = seen.get(key, number)
            except ValueError as exc:
                row.update(status='error', message=str(exc))
            rows.append(row)
    except csv.Error as exc:
        raise ValueError('Unable to read CSV; check quoting and column layout') from exc
    if not rows:
        raise ValueError('CSV has no data rows')
    stage = RegistrationImport(project_id=request.project_id, status='preview', csv_content=request.csv_content,
                               input_sha256=digest(request.csv_content.encode()), plan_sha256='', rows_json=rows,
                               settings_json={**request.model_dump(exclude={'csv_content', 'project_id'}),
                                              'policy': CHEMISTRY_POLICY, 'rdkit_version': rdBase.rdkitVersion})
    stage.plan_sha256 = plan_hash(stage)
    session.add(stage)
    session.flush()
    return stage


def commit_registration(session, stage_id, project_id, expected_hash):
    stage = session.scalar(select(RegistrationImport).where(RegistrationImport.id == stage_id).with_for_update())
    if stage is None or stage.project_id != project_id:
        raise LookupError('Registration preview not found in this project')
    if (expected_hash != stage.plan_sha256 or plan_hash(stage) != stage.plan_sha256
            or digest(stage.csv_content.encode()) != stage.input_sha256):
        raise RegistryConflict('Import preview integrity check failed; prepare a new preview')
    if stage.status == 'committed':
        return stage
    if stage.status != 'preview':
        raise RegistryConflict('Import is not awaiting registration; prepare a new preview')
    if stage.settings_json['rdkit_version'] != rdBase.rdkitVersion or stage.settings_json['policy'] != CHEMISTRY_POLICY:
        raise RegistryConflict('Chemistry version changed after preview; prepare a new preview')
    # Start a write transaction before registration so the whole import is atomic
    # under SQLite as well as PostgreSQL. Retrying a committed preview is read-only.
    stage.status = 'committing'
    session.flush()
    outcomes = []
    for row in stage.rows_json:
        if row['status'] not in {'ready', 'existing'}:
            continue
        record, created = register_compound(session, CompoundInput(**row['registration']),
                                            {'canonical_smiles': row['canonical_smiles'],
                                             'structure_sha256': row['structure_sha256'], 'chemistry': row['chemistry']})
        outcomes.append({'row': row['row'], 'compound_id': record.id, 'created': created})
    stage.outcome_json = {'items': outcomes, 'created': sum(r['created'] for r in outcomes),
                          'existing': sum(not r['created'] for r in outcomes)}
    stage.status = 'committed'
    session.flush()
    return stage


def batch_in_project(session, batch_id, project_id):
    batch = session.get(CompoundBatch, batch_id)
    if batch is None:
        raise LookupError('Batch not found in this project')
    compound = compound_in_project(session, batch.compound_id, project_id)
    return batch, compound


def sample_in_project(session, sample_id, project_id):
    sample = session.get(MaterialSample, sample_id)
    if sample is None:
        raise LookupError('Sample not found in this project')
    batch, compound = batch_in_project(session, sample.batch_id, project_id)
    return sample, batch, compound


def protocol_in_project(session, protocol_id, project_id):
    protocol = session.get(AssayProtocol, protocol_id)
    if protocol is None or protocol.project_id != project_id:
        raise LookupError('Assay protocol not found in this project')
    return protocol


def run_in_project(session, run_id, project_id):
    run = session.get(AssayRun, run_id)
    if run is None:
        raise LookupError('Assay run not found in this project')
    return run, protocol_in_project(session, run.protocol_id, project_id)


def record_observation(session, request):
    run, protocol = run_in_project(session, request.run_id, request.project_id)
    sample, batch, compound = sample_in_project(session, request.sample_id, request.project_id)
    if compound.modality != protocol.modality:
        raise ValueError('Compound modality must match the assay protocol')
    if batch.data_origin != run.data_origin:
        raise ValueError('Synthetic samples and research runs must remain separate')
    if request.units != protocol.units:
        raise ValueError(f'Units must match this protocol exactly ({protocol.units}); no automatic conversion is performed')
    if request.supersedes_id is not None:
        if not request.notes.strip():
            raise ValueError('A correction requires a rationale in its notes')
        original = session.get(AssayObservation, request.supersedes_id)
        if original is None or original.run_id != run.id or original.sample_id != sample.id:
            raise ValueError('A correction must refer to an observation for this same run and sample')
        if session.scalar(select(AssayObservation.id).where(AssayObservation.supersedes_id == original.id)):
            raise RegistryConflict('This observation was already corrected; select the latest correction')
    try:
        value = Decimal(request.value_text.strip())
        numeric = float(value)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError('Enter a finite numeric assay value') from exc
    if not value.is_finite() or not math.isfinite(numeric) or (value != 0 and numeric == 0):
        raise ValueError('Enter a finite numeric assay value')
    observation = AssayObservation(**request.model_dump(exclude={'project_id', 'units'}), numeric_value=numeric)
    session.add(observation)
    session.flush()
    return observation


def observations(session, project_id, compound_id=None, run_id=None):
    query = (select(AssayObservation, AssayRun, AssayProtocol, MaterialSample, CompoundBatch, RegisteredCompound)
             .join(AssayRun, AssayObservation.run_id == AssayRun.id)
             .join(AssayProtocol, AssayRun.protocol_id == AssayProtocol.id)
             .join(MaterialSample, AssayObservation.sample_id == MaterialSample.id)
             .join(CompoundBatch, MaterialSample.batch_id == CompoundBatch.id)
             .join(RegisteredCompound, CompoundBatch.compound_id == RegisteredCompound.id)
             .where(AssayProtocol.project_id == project_id, RegisteredCompound.project_id == project_id)
             .order_by(AssayObservation.id))
    if compound_id is not None:
        query = query.where(RegisteredCompound.id == compound_id)
    if run_id is not None:
        query = query.where(AssayRun.id == run_id)
    records = session.execute(query).all()
    superseded_ids = {row.supersedes_id for row, *_ in records if row.supersedes_id is not None}
    return [{'id': row.id, 'supersedes_id': row.supersedes_id, 'is_current': row.id not in superseded_ids,
             'created_at': row.created_at.isoformat(), 'compound_id': compound.id, 'compound_code': f'CMP-{compound.id:06d}',
             'batch_id': batch.id, 'batch_name': batch.name, 'sample_id': sample.id, 'sample_name': sample.name,
             'protocol_id': protocol.id, 'protocol_name': protocol.name, 'run_id': run.id, 'run_name': run.name,
             'target_id': protocol.target_id, 'endpoint': protocol.endpoint, 'activity_type': protocol.activity_type,
             'modality': protocol.modality, 'units': protocol.units, 'relation': row.relation,
             'value_text': row.value_text, 'numeric_value': row.numeric_value, 'source_record_id': row.source_record_id,
             'source_reference': row.source_reference, 'protocol_source_reference': protocol.source_reference,
             'run_source_reference': run.source_reference, 'sample_source_reference': batch.source_reference,
             'species': protocol.species, 'constructs': protocol.constructs, 'method': protocol.method,
             'conditions': protocol.conditions, 'performed_on': run.performed_on.isoformat(), 'operator': run.operator,
             'data_origin': run.data_origin, 'review_status': 'recorded_unreviewed', 'notes': row.notes}
            for row, run, protocol, sample, batch, compound in records]


def compound_svg(compound):
    drawer = rdMolDraw2D.MolDraw2DSVG(360, 230)
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, Chem.MolFromSmiles(compound.canonical_smiles))
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def search_registry(session, project_id, criteria):
    project_exists(session, project_id)
    records = session.scalars(select(RegisteredCompound).where(RegisteredCompound.project_id == project_id)
                              .order_by(RegisteredCompound.id).limit(10_001)).all()
    if len(records) > 10_000:
        raise ValueError('Registry search is limited to projects with 10,000 compounds')
    query, bits, canonical = None, None, None
    if criteria.match_mode != 'none':
        if criteria.match_mode == 'substructure':
            query = Chem.MolFromSmiles(criteria.query_smiles)
            if query is None or query.GetNumHeavyAtoms() < 2:
                raise ValueError('Enter a valid substructure SMILES with at least two heavy atoms')
        else:
            canonical = structure_record(criteria.query_smiles)['canonical_smiles']
            query = Chem.MolFromSmiles(canonical)
        if criteria.match_mode == 'similarity':
            bits = morgan_bits(query)
    hits = []
    for record in records:
        if criteria.modality and criteria.modality != record.modality:
            continue
        if criteria.name.casefold().strip() not in f'{record.name} {record.notes} CMP-{record.id:06d}'.casefold():
            continue
        props = record.chemistry_json['properties']
        if any((low is not None and props[key] < low) or (high is not None and props[key] > high)
               for key, low, high in [('molecular_weight', criteria.min_mw, criteria.max_mw),
                                      ('logp', criteria.min_logp, criteria.max_logp)]):
            continue
        similarity = None
        if criteria.match_mode == 'exact' and record.canonical_smiles != canonical:
            continue
        if criteria.match_mode == 'substructure' and not Chem.MolFromSmiles(record.canonical_smiles).HasSubstructMatch(query, useChirality=True):
            continue
        if criteria.match_mode == 'similarity':
            similarity = DataStructs.TanimotoSimilarity(bits, morgan_bits(Chem.MolFromSmiles(record.canonical_smiles)))
            if similarity < criteria.min_similarity:
                continue
        hits.append({**compound_summary(record), **props, 'similarity': similarity})
    if criteria.match_mode == 'similarity':
        hits.sort(key=lambda row: (-row['similarity'], row['id']))
    return {'project_id': project_id, 'criteria': criteria.model_dump(), 'criteria_sha256': json_hash(criteria.model_dump()),
            'total_hits': len(hits), 'returned': min(len(hits), criteria.limit), 'items': hits[:criteria.limit],
            'notice': 'Descriptors and Tanimoto similarity describe structures. They do not establish biological activity or model confidence.'}
