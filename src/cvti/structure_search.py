"""Read-only searches over saved project collection structures."""

from rdkit import Chem, DataStructs
from sqlalchemy import select

from cvti.chemistry import morgan_bits, standardize
from cvti.models import Collection, CollectionMolecule, Project


MAX_CANDIDATES = 10_000


def search_collections(session, *, project_id: int, smiles: str, mode: str,
                       collection_id: int | None = None, min_similarity: float = 0.5,
                       limit: int = 500) -> dict:
    """Return structure matches with their saved collection and entry identifiers.

    Similarity is structural Tanimoto on Morgan radius-2, 2048-bit fingerprints;
    it is not a biological activity or applicability score.
    """
    if session.get(Project, project_id) is None:
        raise LookupError('Project not found')
    if mode not in {'exact', 'substructure', 'similarity'}:
        raise ValueError('Search mode must be exact, substructure or similarity')
    if not smiles or len(smiles) > 1000:
        raise ValueError('Enter a SMILES query of at most 1,000 characters')
    if not 0 <= min_similarity <= 1:
        raise ValueError('Minimum similarity must be between 0 and 1')
    if not 1 <= limit <= 1000:
        raise ValueError('Result limit must be between 1 and 1,000')

    if mode == 'substructure':
        query_mol = Chem.MolFromSmiles(smiles)
        if query_mol is None or query_mol.GetNumHeavyAtoms() < 2:
            raise ValueError('Enter a valid substructure SMILES with at least two heavy atoms')
        query_smiles = Chem.MolToSmiles(query_mol, canonical=True, isomericSmiles=True)
    else:
        query_smiles, _ = standardize(smiles)
        query_mol = Chem.MolFromSmiles(query_smiles)
    query_bits = morgan_bits(query_mol) if mode == 'similarity' else None

    stmt = (select(CollectionMolecule, Collection)
            .join(Collection, CollectionMolecule.collection_id == Collection.id)
            .where(Collection.project_id == project_id)
            .order_by(Collection.id, CollectionMolecule.id))
    if collection_id is not None:
        collection = session.get(Collection, collection_id)
        if collection is None or collection.project_id != project_id:
            raise LookupError('Collection not found in this project')
        stmt = stmt.where(Collection.id == collection_id)
    candidates = session.execute(stmt.limit(MAX_CANDIDATES + 1)).all()
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError('Search scope exceeds 10,000 saved entries; select one collection')

    hits = []
    invalid = 0
    for entry, collection in candidates:
        target = Chem.MolFromSmiles(entry.canonical_smiles)
        if target is None:
            invalid += 1
            continue
        similarity = None
        if mode == 'exact':
            matched = entry.canonical_smiles == query_smiles
        elif mode == 'substructure':
            matched = target.HasSubstructMatch(query_mol, useChirality=True)
        else:
            raw_similarity = DataStructs.TanimotoSimilarity(query_bits, morgan_bits(target))
            matched = raw_similarity >= min_similarity
            similarity = raw_similarity
        if matched:
            hits.append({'collection_id': collection.id, 'collection_name': collection.name,
                         'entry_id': entry.id, 'input_smiles': entry.input_smiles,
                         'canonical_smiles': entry.canonical_smiles, 'notes': entry.notes,
                         'similarity': similarity})
    if mode == 'similarity':
        hits.sort(key=lambda row: (-row['similarity'], row['collection_id'], row['entry_id']))
    return {'project_id': project_id, 'collection_id': collection_id, 'mode': mode,
            'query_smiles': query_smiles, 'min_similarity': min_similarity if mode == 'similarity' else None,
            'searched': len(candidates), 'skipped_invalid_structures': invalid,
            'total_hits': len(hits), 'returned': min(len(hits), limit), 'items': hits[:limit],
            'notice': 'Structural matches only. Similarity is not measured activity, model confidence, or a validated applicability domain.'}
