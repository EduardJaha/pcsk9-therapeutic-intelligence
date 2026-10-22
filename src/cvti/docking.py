"""Run the official local Vina executable with preserved preparation and poses."""
import hashlib
import math
from pathlib import Path
import subprocess
import tempfile

from cvti.config import get_settings
from cvti.discovery_models import run_engine


def run_docking(payload):
    settings = get_settings()
    binary = Path(settings.vina_executable).resolve()
    if not binary.is_file():
        raise ValueError('AutoDock Vina is not installed. Configure VINA_EXECUTABLE; see the discovery setup guide.')
    prepared = run_engine('prepare_ligand', payload)
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='cvti-vina-') as folder:
        receptor, ligand, poses = [Path(folder)/name for name in ('receptor.pdbqt','ligand.pdbqt','poses.pdbqt')]
        receptor.write_text(payload['receptor_pdbqt'])
        ligand.write_text(prepared['prepared_ligand_pdbqt'])
        args = [str(binary), '--receptor', str(receptor), '--ligand', str(ligand), '--out', str(poses),
                '--cpu', '1', '--seed', str(payload['seed']), '--exhaustiveness', str(payload['exhaustiveness']),
                '--num_modes', str(payload['n_poses'])]
        for axis, center, size in zip('xyz',payload['center'],payload['box_size']):
            args.extend([f'--center_{axis}',str(center),f'--size_{axis}',str(size)])
        try:
            version = subprocess.run([str(binary),'--version'],capture_output=True,text=True,timeout=10,check=True).stdout.strip()
            result = subprocess.run(args, capture_output=True,text=True,timeout=settings.discovery_timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('Vina timed out; reduce exhaustiveness or box size and submit a new run') from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError('Vina executable cannot run on this host; verify its platform and permissions') from exc
        if result.returncode or not poses.is_file():
            raise ValueError('Vina failed; inspect receptor preparation, atom types and pocket settings')
        text = poses.read_text()
        energies = [[float(v) for v in line.split()[3:6]] for line in text.splitlines() if line.startswith('REMARK VINA RESULT:')]
        if not energies or not all(len(row)==3 and all(math.isfinite(v) for v in row) for row in energies):
            raise ValueError('Vina returned no finite pose energies')
        return {**prepared, 'poses_pdbqt': text, 'energies_kcal_mol': energies,
                'energy_columns': ['vina_score_kcal_mol','rmsd_lower_bound_A','rmsd_upper_bound_A'],
                'vina_version': version, 'vina_executable_sha256': binary_hash,
                'pose_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'settings': {k:payload[k] for k in ('center','box_size','seed','exhaustiveness','n_poses')},
                'log': result.stdout[-20000:]}
