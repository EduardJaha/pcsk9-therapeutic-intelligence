"""Pinned endpoint contracts and local optional model release manifests."""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from cvti.config import get_settings
from cvti.registry import json_hash

SOURCE = 'https://github.com/swansonk14/admet_ai/blob/main/admet_ai/resources/data/admet.csv'
ENDPOINTS = [
    {'id': 'Solubility_AqSolDB', 'name': 'Aqueous solubility', 'task': 'regression', 'units': 'log10(mol/L)', 'category': 'Absorption', 'direction': 'context-dependent', 'species': 'not species-specific'},
    {'id': 'Lipophilicity_AstraZeneca', 'name': 'Lipophilicity', 'task': 'regression', 'units': 'log-ratio', 'category': 'Physicochemical', 'direction': 'context-dependent', 'species': 'not species-specific'},
    {'id': 'Caco2_Wang', 'name': 'Caco-2 permeability', 'task': 'regression', 'units': 'log10(10^-6 cm/s)', 'category': 'Absorption', 'direction': 'context-dependent', 'species': 'human cell assay'},
    {'id': 'Pgp_Broccatelli', 'name': 'P-glycoprotein inhibition', 'task': 'classification', 'units': 'model output [0,1]', 'category': 'Transport', 'direction': 'context-dependent', 'species': 'human P-gp / mouse cells'},
    {'id': 'CYP3A4_Veith', 'name': 'CYP3A4 inhibition', 'task': 'classification', 'units': 'model output [0,1]', 'category': 'Metabolism', 'direction': 'lower inhibition usually preferred', 'species': 'human'},
    {'id': 'CYP2D6_Veith', 'name': 'CYP2D6 inhibition', 'task': 'classification', 'units': 'model output [0,1]', 'category': 'Metabolism', 'direction': 'lower inhibition usually preferred', 'species': 'human'},
    {'id': 'hERG', 'name': 'hERG blocking', 'task': 'classification', 'units': 'model output [0,1]', 'category': 'Toxicity', 'direction': 'lower blocking usually preferred', 'species': 'human'},
    {'id': 'AMES', 'name': 'Ames mutagenicity', 'task': 'classification', 'units': 'model output [0,1]', 'category': 'Toxicity', 'direction': 'lower positive-class score preferred', 'species': 'Salmonella typhimurium'},
    {'id': 'DILI', 'name': 'Drug-induced liver injury', 'task': 'classification', 'units': 'model output [0,1]', 'category': 'Toxicity', 'direction': 'lower positive-class score preferred', 'species': 'human'},
]
for endpoint in ENDPOINTS:
    endpoint.update(source_url=SOURCE, modality='small_molecule', transformation='as returned by pinned model; no inverse transform applied',
                    validation_status='Not independently evaluated in this workspace')


def run_engine(mode, payload, settings=None):
    settings = settings or get_settings()
    # Preserve the venv launcher path: resolving its symlink selects base Python.
    python = Path(settings.discovery_python).absolute()
    if not python.is_file():
        raise ValueError('Optional scientific runtime is missing. Follow docs/discovery-workbench.md to install it locally.')
    bridge = Path(__file__).with_name('discovery_runtime.py')
    with tempfile.TemporaryDirectory(prefix='cvti-science-') as directory:
        input_path, output_path = Path(directory)/'input.json', Path(directory)/'output.json'
        input_path.write_text(json.dumps(payload, allow_nan=False))
        env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'WANDB_MODE': 'disabled', 'OMP_NUM_THREADS': '1'}
        try:
            result = subprocess.run([str(python), '-I', str(bridge), mode, str(input_path), str(output_path)],
                                    env=env, capture_output=True, text=True, timeout=settings.discovery_timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('Scientific engine timed out; reduce the workload and submit a new run') from exc
        if result.returncode or not output_path.is_file():
            # Do not leak input structures or arbitrary runtime logs through errors.
            raise ValueError('Local engine failed. Verify pinned dependencies, checkpoint hashes and input preparation; no result was accepted.')
        if output_path.stat().st_size > 20_000_000:
            raise ValueError('Scientific engine output exceeded the supported size')
        return json.loads(output_path.read_text())


def load_manifest(settings=None):
    settings = settings or get_settings()
    path = Path(settings.admet_manifest)
    if not path.is_file():
        raise ValueError('No local ADMET model manifest. Run the documented inspect command first.')
    manifest = json.loads(path.read_text())
    required = {'provider','package_version','files','dependencies','training_data','overlap_assessment','reuse_review','evaluation','source_url'}
    if not required <= manifest.keys() or manifest['provider'] != 'admet_ai' or manifest['package_version'] != '2.0.1' or not manifest['files']:
        raise ValueError('Unsupported model manifest: this adapter requires pinned ADMET-AI 2.0.1')
    if manifest.get('status') != 'experimental':
        raise ValueError('This adapter only admits experimental models; independent evaluation is not established')
    manifest['endpoint_contracts'] = ENDPOINTS
    manifest['endpoint_contract_sha256'] = json_hash(ENDPOINTS)
    return manifest


def interpret_admet(raw, smiles, endpoints):
    ids = {e['id']: e for e in ENDPOINTS}
    if not endpoints or not set(endpoints) <= ids.keys() or len(set(endpoints)) != len(endpoints):
        raise ValueError('Select distinct supported ADMET endpoints')
    rows = raw.get('rows', [])
    if [r.get('canonical_smiles') for r in rows] != smiles:
        raise ValueError('Prediction identity/order mismatch')
    output = []
    for row in rows:
        for identifier in endpoints:
            endpoint = ids[identifier]
            value = row.get('values', {}).get(identifier)
            if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
                raise ValueError(f'Missing or non-finite prediction for {identifier}')
            if endpoint['task'] == 'classification' and not 0 <= value <= 1:
                raise ValueError(f'Out-of-range classification output for {identifier}')
            output.append({'canonical_smiles': row['canonical_smiles'], **endpoint, 'value': value,
                           'data_kind': 'predicted', 'confidence': None, 'applicability': 'unknown',
                           'calibration': 'not independently evaluated', 'training_overlap': 'unknown'})
    return {'results': output, 'runtime': raw.get('runtime'),
            'notice': 'Experimental pretrained endpoint predictions. No calibrated confidence, PCSK9 activity, clinical safety or efficacy is established. No composite success score is calculated.'}


if __name__ == '__main__':
    manifest = run_engine('inspect', {})
    path = Path(get_settings().admet_manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))
    print(f'Local experimental model manifest written to {path}; register it from Endpoint predictions.')
