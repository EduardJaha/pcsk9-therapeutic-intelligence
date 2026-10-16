"""Persistent row-by-row jobs processed by one cooperative local worker."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from cvti.config import get_settings
from cvti.models import BatchJob, Experiment, Project, utcnow
from cvti.workbench import molecule_profile


def submit_batch(session, csv_content, smiles_column, *, experiment_id=None, project_id=1, save=False):
    if session.get(Project, project_id) is None:
        raise ValueError('Project not found')
    if experiment_id is not None and session.get(Experiment, experiment_id) is None:
        raise ValueError('Experiment not found')
    if save and experiment_id is None:
        raise ValueError('Saving predictions requires an explicitly selected model')
    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        if not reader.fieldnames or smiles_column not in reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Select an existing, unambiguous SMILES column')
        rows = []
        for index, row in enumerate(reader, start=2):
            if len(rows) >= get_settings().batch_max_rows:
                raise ValueError(f'Batch row limit exceeded ({get_settings().batch_max_rows})')
            rows.append({'csv_line': index, 'input_smiles': (row.get(smiles_column) or '').strip(),
                         'input': {k: v for k, v in row.items() if k is not None}})
    except csv.Error as exc:
        raise ValueError('Unable to read CSV') from exc
    if not rows:
        raise ValueError('CSV has no data rows')
    job = BatchJob(project_id=project_id, experiment_id=experiment_id, save_predictions=save,
                   input_rows=rows, result_rows=[], status='queued')
    session.add(job)
    session.commit()
    return job


def process_next(factory):
    from cvti.ml import predict
    with factory() as session:
        job = session.scalar(select(BatchJob).where(BatchJob.status == 'queued').order_by(BatchJob.id))
        if job is None:
            return None
        claimed = session.execute(update(BatchJob).where(BatchJob.id == job.id, BatchJob.status == 'queued')
                                  .values(status='running', updated_at=utcnow())).rowcount
        session.commit()
        if not claimed:
            return None
        results = list(job.result_rows)
        seen = {row['canonical_smiles'] for row in results if row.get('canonical_smiles') and row.get('status') == 'ok'}
        try:
            for original in job.input_rows[len(results):]:
                result = {**original, 'experiment_id': job.experiment_id, 'project_id': job.project_id}
                try:
                    if not 1 <= len(original['input_smiles']) <= 1000:
                        raise ValueError('SMILES must contain 1 to 1000 characters')
                    profile = molecule_profile(original['input_smiles'])
                    canonical = profile['canonical_smiles']
                    result['canonical_smiles'] = canonical
                    if canonical in seen:
                        result.update(status='duplicate', message='Same standardized structure already processed in this batch')
                    else:
                        result.update(status='ok', properties=profile['properties'], formula=profile['formula'])
                        if job.experiment_id is not None:
                            # Prediction and result checkpoint are committed together to avoid retry duplicates.
                            predicted = predict(session, canonical, job.experiment_id, save=False, project_id=job.project_id)
                            if job.save_predictions:
                                from cvti.models import Prediction
                                record = Prediction(project_id=job.project_id, experiment_id=job.experiment_id,
                                                    input_smiles=original['input_smiles'], canonical_smiles=canonical,
                                                    probability=predicted['probability_exploratory_activity'])
                                session.add(record)
                                session.flush()
                                predicted['prediction_id'] = record.id
                            result['prediction'] = predicted
                        seen.add(canonical)
                except (ValueError, FileNotFoundError) as exc:
                    result.update(status='error', message=str(exc))
                results.append(result)
                job.result_rows = list(results)
                job.updated_at = utcnow()
                session.commit()
            job.status = 'completed'
            job.updated_at = utcnow()
            session.commit()
        except Exception:
            session.rollback()
            job = session.get(BatchJob, job.id)
            job.status = 'interrupted'
            job.error = 'Worker interrupted; completed rows are preserved. Inspect and explicitly retry.'
            job.updated_at = utcnow()
            session.commit()
            raise
        return job.id


def recover_jobs(factory):
    """Call only after acquiring the exclusive worker lock: no live worker can own these."""
    with factory() as session:
        session.execute(update(BatchJob).where(BatchJob.status == 'running').values(
            status='interrupted', error='Previous worker stopped; completed rows retained', updated_at=utcnow()))
        session.commit()


def retry_batch(session, identifier):
    job = session.get(BatchJob, identifier)
    if job is None:
        raise ValueError('Batch job not found')
    if job.status not in {'interrupted', 'failed'}:
        raise ValueError('Only interrupted or failed jobs can be retried')
    job.status, job.error, job.updated_at = 'queued', None, utcnow()
    session.commit()
    return job


def job_summary(job, include_rows=False):
    output = {'id': job.id, 'project_id': job.project_id, 'experiment_id': job.experiment_id,
              'status': job.status, 'created_at': job.created_at.isoformat(), 'updated_at': job.updated_at.isoformat(),
              'rows': len(job.input_rows), 'processed': len(job.result_rows), 'save_predictions': job.save_predictions,
              'error': job.error}
    if include_rows:
        output['results'] = job.result_rows
    return output


def csv_export(rows):
    """Encode external text safely for spreadsheet consumers."""
    keys = list(dict.fromkeys(k for row in rows for k in row))
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=keys)
    writer.writeheader()
    for row in rows:
        encoded = {}
        for key, value in row.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, sort_keys=True)
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                value = "'" + value
            encoded[key] = value
        writer.writerow(encoded)
    return output.getvalue()
