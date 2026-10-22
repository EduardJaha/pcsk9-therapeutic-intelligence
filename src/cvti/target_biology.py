"""Explicit public identifier lookups with source snapshots; no compound uploads."""
import hashlib
import re

import httpx

from cvti.models import utcnow


def target_dossier(ensembl_id, pdb_id=None):
    if not re.fullmatch(r'ENSG[0-9]{11}', ensembl_id):
        raise ValueError('Enter a human Ensembl gene identifier (ENSG followed by 11 digits)')
    if pdb_id and not re.fullmatch(r'[0-9][A-Za-z0-9]{3}', pdb_id):
        raise ValueError('Enter a four-character PDB identifier')
    url = 'https://api.platform.opentargets.org/api/v4/graphql'
    query = 'query Target($id:String!){target(ensemblId:$id){id approvedSymbol approvedName associatedDiseases(page:{index:0,size:30}){count rows{score disease{id name}}}}}'
    snapshots = []
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(url, json={'query': query, 'variables': {'id': ensembl_id}})
            response.raise_for_status()
            payload = response.json()
            target = (payload.get('data') or {}).get('target')
            if payload.get('errors') or not target or target.get('id') != ensembl_id:
                raise ValueError('Open Targets returned no matching target or an incomplete response')
            snapshots.append({'url': url, 'query': query, 'variables': {'id': ensembl_id},
                              'retrieved_at': utcnow().isoformat(), 'sha256': hashlib.sha256(response.content).hexdigest(),
                              'response_text': response.text})
            structure = None
            if pdb_id:
                structure_url = f'https://data.rcsb.org/rest/v1/core/entry/{pdb_id.upper()}'
                response = client.get(structure_url)
                response.raise_for_status()
                structure = response.json()
                snapshots.append({'url': structure_url, 'retrieved_at': utcnow().isoformat(),
                                  'sha256': hashlib.sha256(response.content).hexdigest(), 'response_text': response.text})
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise ValueError('Public target source unavailable; no replacement or synthetic evidence was generated') from exc
    return {'target': target, 'structure_metadata': structure, 'sources': snapshots,
            'target_url': f'https://platform.opentargets.org/target/{ensembl_id}',
            'structure_url': f'https://www.rcsb.org/structure/{pdb_id.upper()}' if pdb_id else None,
            'notice': 'Public target associations are context, not compound efficacy. A supplied PDB is not automatically verified to match the target, construct or assay; review chains, mutations and pocket biology.'}
