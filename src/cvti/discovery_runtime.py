"""Isolated optional engine bridge. Run by a configured local Python, never a shell.

Only this file is imported in the optional environment. Inputs/outputs are local
JSON files. Network connections are disabled before importing scientific engines.
"""
import hashlib
import importlib.metadata
import json
import math
import socket
import sys
from pathlib import Path


def no_network(*args, **kwargs):
    raise RuntimeError('Network access is disabled during local scientific inference')


socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.create_connection = no_network


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def inspect_model():
    import importlib.util
    root = Path(importlib.util.find_spec('admet_ai').origin).parent / 'resources' / 'models'
    files = {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*.pt'))}
    if not files:
        raise ValueError('No bundled ADMET-AI checkpoints are installed')
    return {'provider': 'admet_ai', 'package_version': importlib.metadata.version('admet_ai'),
            'models_dir': str(root), 'files': files,
            'source_url': 'https://github.com/swansonk14/admet_ai', 'code_license': 'MIT',
            'status': 'experimental', 'modality': 'small_molecule',
            'training_data': 'TDC ADMET datasets; endpoint-specific source definitions',
            'overlap_assessment': 'Unknown for this workspace; no independent evaluation performed',
            'reuse_review': 'Upstream MIT code; dataset and checkpoint use must be reviewed for the intended distribution',
            'evaluation': 'Upstream evidence only; no local calibration or prospective validation',
            'dependencies': {k: importlib.metadata.version(k) for k in ('admet_ai','chemprop','torch','rdkit')}}


def admet(payload):
    manifest = payload['manifest']
    current = inspect_model()
    if any(current[k] != manifest[k] for k in ('provider', 'package_version', 'files', 'dependencies')):
        raise ValueError('ADMET runtime or checkpoint checksum changed; register the new model release')
    # Always load the installed package location, never a request-supplied path.
    from admet_ai import ADMETModel
    model = ADMETModel(models_dir=current['models_dir'], include_physchem=False, drugbank_path=None, num_workers=0)
    frame = model.predict(payload['smiles'])
    if list(frame.index) != payload['smiles']:
        raise ValueError('ADMET output molecule identities do not match the requested order')
    return {'rows': [{'canonical_smiles': str(smiles), 'values': {k: float(v) for k,v in row.items()}}
                     for smiles,row in frame.iterrows()], 'runtime': current['dependencies']}


def prepare_ligand(payload):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from meeko import MoleculePreparation, PDBQTWriterLegacy
    mol = Chem.AddHs(Chem.MolFromSmiles(payload['canonical_smiles']))
    params = AllChem.ETKDGv3()
    params.randomSeed = payload['seed']
    params.maxIterations = 500
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise ValueError('Ligand embedding failed')
    optimization = None
    if AllChem.MMFFHasAllMoleculeParams(mol):
        optimization = AllChem.MMFFOptimizeMolecule(mol, maxIters=300) == 0
    setups = MoleculePreparation().prepare(mol)
    if len(setups) != 1:
        raise ValueError('Ligand preparation produced ambiguous setups')
    ligand, success, message = PDBQTWriterLegacy.write_string(setups[0])
    if not success:
        raise ValueError('Ligand PDBQT preparation failed')
    return {'prepared_ligand_pdbqt': ligand,
            'ligand_optimization_converged': optimization,
            'receptor_sha256': hashlib.sha256(payload['receptor_pdbqt'].encode()).hexdigest(),
            'runtime': {k: importlib.metadata.version(k) for k in ('meeko','rdkit')},
            'notice': 'Rigid-receptor Vina hypothesis, not measured affinity. User-supplied receptor preparation and pocket require review. Ligand pH/protonation is not optimized; no automatic PCSK9–LDLR conclusion.'}


if __name__ == '__main__':
    mode, input_path, output_path = sys.argv[1:]
    payload = json.loads(Path(input_path).read_text())
    result = inspect_model() if mode == 'inspect' else admet(payload) if mode == 'admet' else prepare_ligand(payload) if mode == 'prepare_ligand' else None
    if result is None:
        raise ValueError('Unsupported scientific engine')
    Path(output_path).write_text(json.dumps(result, allow_nan=False))
