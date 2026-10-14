import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.Scaffolds import MurckoScaffold


_fingerprinter = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def standardize(smiles: str) -> tuple[str, str]:
    """Return charge-parent canonical SMILES and its Bemis–Murcko scaffold."""
    mol = Chem.MolFromSmiles(smiles or "")
    if mol is None or mol.GetNumHeavyAtoms() < 2:
        raise ValueError("Invalid or unsupported SMILES")
    mol = rdMolStandardize.ChargeParent(mol)
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=False)
    if not scaffold:
        raise ValueError("A ring scaffold is required for scaffold-aware evaluation")
    return canonical, scaffold


def fingerprint(smiles: str) -> np.ndarray:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Invalid SMILES")
    bits = _fingerprinter.GetFingerprint(mol)
    array = np.zeros((2048,), dtype=np.int8)
    DataStructs.ConvertToNumpyArray(bits, array)
    return array
