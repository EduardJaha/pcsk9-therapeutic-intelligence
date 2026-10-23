"""Local structure exploration. No measurements, activity models or approvals."""
import csv
import io
import math

from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import AllChem, Descriptors, FilterCatalog, QED, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem.Scaffolds import MurckoScaffold

from cvti.chemistry import morgan_bits
from cvti.registry import json_hash, structure_record


def molecule(smiles):
    record = structure_record(smiles)
    mol = Chem.MolFromSmiles(record['canonical_smiles'])
    if mol.GetNumHeavyAtoms() > 150:
        raise ValueError('Local discovery tools support at most 150 heavy atoms per molecule')
    return record, mol


def dossier(smiles):
    record, mol = molecule(smiles)
    props = record['chemistry']['properties']
    props.update(exact_mass=round(Descriptors.ExactMolWt(mol), 4),
                 fraction_sp3=round(rdMolDescriptors.CalcFractionCSP3(mol), 3),
                 ring_count=rdMolDescriptors.CalcNumRings(mol),
                 aromatic_rings=rdMolDescriptors.CalcNumAromaticRings(mol),
                 formal_charge=Chem.GetFormalCharge(mol), heavy_atoms=mol.GetNumHeavyAtoms(),
                 qed=round(QED.qed(mol), 3))
    params = FilterCatalog.FilterCatalogParams()
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK)
    catalog = FilterCatalog.FilterCatalog(params)
    alerts = [{'description': hit.GetDescription(), 'catalog': hit.GetProp('FilterSet'),
               'interpretation': 'Substructure flag requiring review; not proof of toxicity or assay interference'}
              for hit in catalog.GetMatches(mol)]
    checks = [('Molecular weight ≤ 500', props['molecular_weight'] <= 500),
              ('Calculated logP ≤ 5', props['logp'] <= 5),
              ('H-bond donors ≤ 5', props['h_bond_donors'] <= 5),
              ('H-bond acceptors ≤ 10', props['h_bond_acceptors'] <= 10)]
    draw = rdMolDraw2D.MolDraw2DSVG(480, 300)
    rdMolDraw2D.PrepareAndDrawMolecule(draw, mol)
    draw.FinishDrawing()
    return {**record, 'input_smiles': smiles, 'svg': draw.GetDrawingText(),
            'scaffold': MurckoScaffold.MurckoScaffoldSmiles(mol=mol),
            'properties': props, 'alerts': alerts,
            'rules': [{'rule': name, 'passes': passes} for name, passes in checks],
            'provenance': {'engine': 'RDKit', 'version': rdBase.rdkitVersion, 'policy': 'discovery-v1',
                           'input_sha256': json_hash({'smiles': smiles})},
            'notice': 'Calculated properties and heuristic flags. QED and rule checks do not predict efficacy, safety or synthetic feasibility.'}


def conformer(smiles, seed=2026):
    record, mol = molecule(smiles)
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    params.maxIterations = 500
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise ValueError('3D embedding failed; no conformation was generated')
    method, converged = 'ETKDGv3 only', None
    if AllChem.MMFFHasAllMoleculeParams(mol):
        method = 'ETKDGv3 + MMFF94'
        converged = AllChem.MMFFOptimizeMolecule(mol, maxIters=300) == 0
    conf = mol.GetConformer()
    atoms = [{'element': atom.GetSymbol(), 'xyz': list(conf.GetAtomPosition(atom.GetIdx()))}
             for atom in mol.GetAtoms()]
    return {'canonical_smiles': record['canonical_smiles'], 'atoms': atoms,
            'bonds': [[b.GetBeginAtomIdx(), b.GetEndAtomIdx(), b.GetBondTypeAsDouble()] for b in mol.GetBonds()],
            'sdf': Chem.MolToMolBlock(mol) + '\n$$$$\n', 'method': method, 'seed': seed,
            'optimization_converged': converged, 'rdkit_version': rdBase.rdkitVersion,
            'notice': 'One generated conformer, not a measured or bound conformation. Protonation is not optimized for pH.'}


def screen(query, structures, min_similarity=0.0):
    _, ref = molecule(query)
    fp = morgan_bits(ref)
    rows, errors, seen = [], [], set()
    for index, smiles in enumerate(structures, 1):
        try:
            record, mol = molecule(smiles)
            canonical = record['canonical_smiles']
            if canonical in seen:
                errors.append({'row': index, 'input_smiles': smiles, 'message': 'Duplicate standardized structure'})
                continue
            seen.add(canonical)
            similarity = float(DataStructs.TanimotoSimilarity(fp, morgan_bits(mol)))
            if similarity >= min_similarity:
                rows.append({'row': index, 'canonical_smiles': canonical, 'similarity': similarity,
                             **record['chemistry']['properties']})
        except ValueError as exc:
            errors.append({'row': index, 'input_smiles': smiles, 'message': str(exc)})
    rows.sort(key=lambda r: (-r['similarity'], r['canonical_smiles']))
    return {'results': rows, 'errors': errors, 'submitted': len(structures),
            'method': 'Morgan radius 2 / 2048 bits / Tanimoto', 'rdkit_version': rdBase.rdkitVersion,
            'notice': 'Structural similarity only. No target affinity or activity is inferred.'}


def sar(csv_content, similarity_threshold=0.5):
    """Only exact concentration observations from one explicitly identified assay."""
    reader = csv.DictReader(io.StringIO(csv_content))
    context = ['target', 'endpoint', 'assay_id', 'modality', 'units', 'data_origin']
    required = ['smiles', 'value', 'relation', 'source_reference'] + context
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not set(required) <= set(reader.fieldnames):
        raise ValueError('SAR CSV requires columns: ' + ', '.join(required))
    rows = []
    for raw in reader:
        if len(rows) >= 100:
            raise ValueError('SAR is limited to 100 observations per analysis')
        if any(not (raw.get(k) or '').strip() for k in required):
            raise ValueError('All SAR context and source fields must be supplied')
        rows.append({k: raw[k].strip() for k in required})
    if len(rows) < 2:
        raise ValueError('At least two observations are required')
    if len({tuple(row[k] for k in context) for row in rows}) != 1:
        raise ValueError('Use one target, endpoint, assay, modality, unit and data origin; mixed measurements cannot be pooled')
    units = {'M': 1., 'mM': 1e-3, 'uM': 1e-6, 'µM': 1e-6, 'nM': 1e-9, 'pM': 1e-12}
    if rows[0]['endpoint'] not in {'IC50', 'EC50', 'Ki', 'Kd'} or rows[0]['units'] not in units:
        raise ValueError('Use IC50, EC50, Ki or Kd with molar concentration units')
    if rows[0]['data_origin'] not in {'experimental', 'synthetic'} or rows[0]['modality'] != 'small_molecule':
        raise ValueError('Use an experimental or synthetic small-molecule assay series')
    fps, seen = [], set()
    for row in rows:
        if row['relation'] != '=':
            raise ValueError('Censored measurements cannot be used for numerical activity cliffs')
        value = float(row['value'])
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Activity concentrations must be finite and positive')
        record, mol = molecule(row['smiles'])
        canonical = record['canonical_smiles']
        if canonical in seen:
            raise ValueError('Repeated structures require an explicitly reviewed aggregation outside this analysis')
        seen.add(canonical)
        row.update(canonical_smiles=canonical, p_activity=-math.log10(value * units[row['units']]))
        fps.append(morgan_bits(mol))
    pairs = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            similarity = float(DataStructs.TanimotoSimilarity(fps[i], fps[j]))
            if similarity < similarity_threshold:
                continue
            delta = abs(rows[i]['p_activity'] - rows[j]['p_activity'])
            pairs.append({'a': rows[i]['canonical_smiles'], 'b': rows[j]['canonical_smiles'],
                          'similarity': similarity, 'absolute_delta_p_activity': delta,
                          'sali': delta / (1 - similarity) if similarity < 1 else None,
                          'fingerprint_collision': similarity == 1,
                          'activity_cliff': delta >= 1, 'source_a': rows[i]['source_reference'],
                          'source_b': rows[j]['source_reference']})
    pairs.sort(key=lambda p: -p['absolute_delta_p_activity'])
    return {'observations': rows, 'pairs': pairs, 'context': {k: rows[0][k] for k in context},
            'input_sha256': json_hash({'csv': csv_content}), 'similarity_threshold': similarity_threshold,
            'rdkit_version': rdBase.rdkitVersion,
            'notice': 'Exploratory same-assay activity cliffs (≥1 log unit). These are similarity pairs, not verified matched molecular pairs; no assay approval or training import occurs.'}


TRANSFORMS = {
    'Phenol O-methylation': '[c:1][OH1:2]>>[c:1][O:2]C',
    'Aryl methyl addition': '[cH:1]>>[c:1]C',
    'Aryl fluorination': '[cH:1]>>[c:1]F',
}


def analogs(smiles, transformations):
    record, mol = molecule(smiles)
    reference = morgan_bits(mol)
    seen, rows = {record['canonical_smiles']}, []
    for name in transformations:
        if name not in TRANSFORMS:
            raise ValueError('Unknown transformation')
        reaction = AllChem.ReactionFromSmarts(TRANSFORMS[name])
        for products in reaction.RunReactants((mol,), maxProducts=60):
            product = products[0]
            try:
                Chem.SanitizeMol(product)
                canonical = Chem.MolToSmiles(product, isomericSmiles=True)
                if canonical in seen or product.GetNumHeavyAtoms() > 150:
                    continue
                seen.add(canonical)
                rows.append({'canonical_smiles': canonical, 'transformation': name,
                             'similarity_to_parent': float(DataStructs.TanimotoSimilarity(reference, morgan_bits(product))),
                             'molecular_weight': round(Descriptors.MolWt(product), 2),
                             'logp': round(Descriptors.MolLogP(product), 2), 'qed': round(QED.qed(product), 3)})
            except (ValueError, RuntimeError):
                continue
    rows.sort(key=lambda r: r['canonical_smiles'])
    # Diversity selection only: do not claim activity improvement or active learning.
    selected, remaining = [], list(rows)
    if remaining:
        selected.append(remaining.pop(0))
    while remaining and len(selected) < 8:
        best = min(remaining, key=lambda r: max(DataStructs.TanimotoSimilarity(
            morgan_bits(Chem.MolFromSmiles(r['canonical_smiles'])),
            morgan_bits(Chem.MolFromSmiles(s['canonical_smiles']))) for s in selected))
        selected.append(best)
        remaining.remove(best)
    return {'parent': record['canonical_smiles'], 'candidates': rows,
            'diverse_shortlist': [r['canonical_smiles'] for r in selected],
            'transformations': {name: TRANSFORMS[name] for name in transformations},
            'rdkit_version': rdBase.rdkitVersion,
            'notice': 'Enumerated structural hypotheses, not a synthesis plan or predicted improvement. Shortlist uses fingerprint diversity only; no potency, safety or feasibility is established.'}
