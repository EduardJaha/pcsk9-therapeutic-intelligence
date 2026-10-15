"""Calculated molecular profiles and comparison geometry for the research UI."""

import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from sklearn.decomposition import PCA

from cvti.chemistry import fingerprint, standardize


def molecule_profile(smiles: str) -> dict:
    canonical, scaffold = standardize(smiles)
    molecule = Chem.MolFromSmiles(canonical)
    drawer = rdMolDraw2D.MolDraw2DSVG(360, 230)
    drawer.drawOptions().clearBackground = False
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, molecule)
    drawer.FinishDrawing()
    return {
        "input_smiles": smiles, "canonical_smiles": canonical, "scaffold": scaffold,
        "formula": rdMolDescriptors.CalcMolFormula(molecule),
        "svg": drawer.GetDrawingText(),
        "properties": {
            "molecular_weight": round(Descriptors.MolWt(molecule), 2),
            "logp": round(Descriptors.MolLogP(molecule), 2),
            "tpsa": round(rdMolDescriptors.CalcTPSA(molecule), 2),
            "h_bond_donors": rdMolDescriptors.CalcNumHBD(molecule),
            "h_bond_acceptors": rdMolDescriptors.CalcNumHBA(molecule),
            "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(molecule),
        },
        "notice": "Calculated molecular descriptors; not measured ADMET or evidence of therapeutic efficacy.",
    }


def chemical_space(profiles: list[dict]) -> dict:
    """Fit a local PCA to only the compared structures, with no activity labels."""
    structures = [profile["canonical_smiles"] for profile in profiles]
    if len(set(structures)) != len(structures):
        raise ValueError("Use distinct standardized molecules for comparison")
    matrix = np.stack([fingerprint(smiles) for smiles in structures]).astype(float)
    if not np.any(np.var(matrix, axis=0)):
        coordinates = np.zeros((len(structures), 2))
        variance = [0.0, 0.0]
    else:
        projection = PCA(n_components=2, svd_solver="full")
        coordinates = projection.fit_transform(matrix)
        variance = [float(value) for value in projection.explained_variance_ratio_]
    return {"method": "Morgan fingerprint PCA of compared molecules only",
            "explained_variance_ratio": variance,
            "points": [{"molecule": f"Molecule {index + 1}", "canonical_smiles": smiles,
                        "pc1": float(coordinates[index, 0]), "pc2": float(coordinates[index, 1])}
                       for index, smiles in enumerate(structures)],
            "notice": "Relative structural positions change with the comparison set; this is not a validated applicability domain."}
