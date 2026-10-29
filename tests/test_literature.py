import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from cvti.api import create_app
from cvti import assistant, literature as lab, literature_sources as sources
from cvti.config import Settings
from cvti.db import make_engine, session_factory
from cvti.models import LiteratureRecord

JATS = b'''<article><front><article-meta><article-id pub-id-type="pmc">123</article-id>
<permissions>CC BY test fixture</permissions><abstract><p>Synthetic fixture.</p></abstract></article-meta></front>
<body><sec><title>Methods</title><p>Human PCSK9 wild type and LDLR. ELISA absorbance 450 nm.
SBC positive control; DMSO negative control; three replicates.</p></sec><sec><title>Results</title>
<table-wrap id="T3"><label>Table 3</label><caption><p>Direct PCSK9-LDLR IC50 (nM), mean SD.</p></caption>
<table><tr><th>Compound</th><th>IC50</th><th>SD</th></tr><tr><td>TestA</td><td>0.8</td><td>1.0</td></tr></table>
<table-wrap-foot><p>Three experiments.</p></table-wrap-foot></table-wrap></sec></body></article>'''


@pytest.fixture
def workspace(tmp_path):
    url = f'sqlite:///{tmp_path / "literature.db"}'
    with TestClient(create_app(url, str(tmp_path / 'artifacts'))) as api:
        engine = make_engine(url)
        yield api, session_factory(engine)
        engine.dispose()


def source(factory):
    with factory() as session:
        search = lab.save(session, 1, 'search', {'query': 'synthetic fixture', 'providers': {},
            'coverage': 'Synthetic fixture only', 'publications': []})
        publication = lab.save(session, 1, 'publication', {'title': 'Synthetic fixture',
            'pmcid': 'PMC123', 'url': 'https://example.test/source'}, parent_id=search.id)
        return lab.save(session, 1, 'document', {**sources.parse_jats(JATS), 'title': 'Synthetic fixture',
                        'format': 'xml'}, parent_id=publication.id, content=JATS)


def assay():
    data = {k: None for k, v in lab.AssayDraft.model_fields.items()}
    data.update(endpoint='direct_ppi', activity_type='IC50', modality='small_molecule', uncertainty_type='SD',
        endpoint_evidence={'text': 'Direct PCSK9-LDLR IC50 (nM), mean SD.', 'passage_id': 'P3'},
        compound={'text': 'TestA', 'passage_id': 'P3'}, value={'text': '0.8', 'passage_id': 'P3'},
        units={'text': 'nM', 'passage_id': 'P3'}, uncertainty={'text': '1.0', 'passage_id': 'P3'})
    return data


def local_model(monkeypatch, generated=None, *, digest_changed=False, incomplete=False):
    settings = Settings(_env_file=None, assistant_model='local-test')
    monkeypatch.setattr(assistant, 'get_settings', lambda: settings)
    calls = []
    statuses = [0]
    def status():
        statuses[0] += 1
        return {'ready': True, 'model': 'local-test', 'provider': 'ollama_local',
                'digest': ('b' if digest_changed and statuses[0] > 1 else 'a') * 64}
    monkeypatch.setattr(assistant, 'model_status', status)
    def handler(request):
        calls.append(json.loads(request.content))
        resolved = generated or {'assays': [assay()], 'gaps': ['Synthetic fixture only']}
        catalog = {p['id']: lab.quote_catalog(p) for p in sources.parse_jats(JATS)['passages']}
        selected = []
        for row in resolved['assays']:
            facts = {}
            for field, value in row.items():
                if isinstance(value, dict):
                    quote = next((q['quote_id'] for q in catalog[value['passage_id']] if q['text'] == value['text']), 'Q9999')
                    facts[field] = value['passage_id'] + ':' + quote
            selected.append({k: row[k] for k in ('endpoint', 'activity_type', 'modality', 'uncertainty_type')} | facts)
        return httpx.Response(200, json={'model': 'local-test', 'done': True,
            'done_reason': 'length' if incomplete else 'stop',
            'message': {'content': json.dumps({'assays': selected, 'gaps': resolved['gaps']})}})
    monkeypatch.setattr(assistant, '_client', lambda s: httpx.Client(transport=httpx.MockTransport(handler),
                                                                   base_url='http://127.0.0.1'))
    return calls


def test_pubmed_article_identity_does_not_use_reference_ids_and_search_is_bounded(monkeypatch):
    monkeypatch.setattr(sources.time, 'sleep', lambda n: None)
    def handler(request):
        if request.url.path.endswith('esearch.fcgi'):
            assert request.url.params['mindate'] == '2023/01/01'
            return httpx.Response(200, json={'esearchresult': {'idlist': ['1'], 'count': '20'}})
        if request.url.path.endswith('efetch.fcgi'):
            return httpx.Response(200, content=b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID>
                <Article><ArticleTitle>Real title</ArticleTitle></Article></MedlineCitation><PubmedData>
                <ArticleIdList><ArticleId IdType="pmc">PMC123</ArticleId><ArticleId IdType="doi">10/test</ArticleId></ArticleIdList>
                <ReferenceList><Reference><ArticleIdList><ArticleId IdType="pmc">PMC999</ArticleId></ArticleIdList></Reference></ReferenceList>
                </PubmedData></PubmedArticle></PubmedArticleSet>''')
        assert 'FIRST_PDATE:[2023-01-01 TO 2026-10-29]' in request.url.params['query']
        return httpx.Response(200, json={'hitCount': 1, 'resultList': {'result': [
            {'id': '1', 'source': 'MED', 'pmid': '1', 'pmcid': 'PMC123', 'title': 'Real title'}]}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = sources.search('PCSK9', 1, client, '2023-01-01', '2026-10-29')
    assert len(result['publications']) == 1
    assert result['publications'][0]['pmcid'] == 'PMC123'
    assert result['providers']['pubmed']['status'] == 'capped'
    assert len(result['response_log']) == 3 and result['response_log'][0]['body_base64']


def test_partial_search_and_pdf_or_xml_failures_are_explicit(monkeypatch):
    monkeypatch.setattr(sources.time, 'sleep', lambda n: None)
    def handler(request):
        return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = sources.search('PCSK9', 1, client)
    assert all(p['status'] == 'failed' for p in result['providers'].values())
    assert result['response_log']
    with pytest.raises(ValueError, match='PDF'):
        sources.parse_pdf(b'<html>access challenge</html>')
    with pytest.raises(ValueError, match='entity'):
        sources.parse_jats(b'<!ENTITY evil "test"><article/>')
    with pytest.raises(ValueError, match='PMC'):
        sources.download('http://localhost/private', 'xml')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=JATS))) as client:
        with pytest.raises(ValueError, match='identity'):
            sources.download('PMC999', 'xml', client)


def test_jats_preserves_methods_tables_footnotes_and_caveats():
    parsed = sources.parse_jats(JATS)
    assert parsed['passages'][1]['locator'].startswith('Full text / Methods')
    assert 'TestA | 0.8 | 1.0' in parsed['passages'][2]['text']
    assert 'Three experiments.' in parsed['passages'][2]['text']
    assert parsed['license'] == 'CC BY test fixture'
    assert parsed['limitations']
    assert sources.parse_jats(b'<article><front><article-meta><abstract>Only abstract.</abstract></article-meta></front></article>')['text_scope'] == 'abstract_only'


def synthetic_pdf():
    stream = b'BT /F1 12 Tf 40 100 Td (Synthetic assay methods, IC50 10 nM) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    result, offsets = b'%PDF-1.4\n', [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += str(i).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    start = len(result)
    result += b'xref\n0 6\n0000000000 65535 f \n'
    result += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return result + f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode()


def test_pdf_processing_and_current_pmc_public_dataset(monkeypatch):
    monkeypatch.setattr(sources.time, 'sleep', lambda n: None)
    raw = synthetic_pdf()
    parsed = sources.parse_pdf(raw)
    assert 'IC50 10 nM' in parsed['passages'][0]['text']
    assert parsed['passages'][0]['locator'].startswith('PDF page 1')
    def handler(request):
        if request.url.host == 'pmc.ncbi.nlm.nih.gov':
            return httpx.Response(200, content=b'<html>challenge</html>')
        if request.url.params.get('list-type'):
            return httpx.Response(200, content=b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><CommonPrefixes><Prefix>PMC123.2/</Prefix></CommonPrefixes></ListBucketResult>')
        if request.url.path.endswith('.json'):
            return httpx.Response(200, json={'pmcid': 'PMC123', 'version': 2, 'license_code': 'CC BY',
                'pdf_url': 's3://pmc-oa-opendata/PMC123.2/PMC123.2.pdf'})
        return httpx.Response(200, content=raw)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        actual, data = sources.download('PMC123', 'pdf', client)
    assert actual == raw and data['repository_prefix'] == 'PMC123.2/'
    assert data['repository_metadata']['license_code'] == 'CC BY'


def test_extraction_evidence_isolation_provenance_and_training_unchanged(workspace, monkeypatch):
    api, factory = workspace
    document = source(factory)
    calls = local_model(monkeypatch)
    before = api.get('/summary').json()
    response = api.post('/literature/extract', json={'document_id': document.id, 'passage_ids': ['P3']})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['payload']['model']['digest'] == 'a' * 64
    assert 'uncertainty_at_least_point_estimate' in result['payload']['assays'][0]['flags']
    assert 'Human PCSK9' not in calls[0]['messages'][1]['content']
    assert result['payload']['coverage']['selected'] == 1
    assert api.get('/summary').json() == before
    report = api.post('/literature/reports', json={'extraction_ids': [result['id']]}).json()
    assert 'Table 3' in report['markdown'] and document.content_sha256 in report['markdown']
    review = {'extraction_id': result['id'], 'reviewer': 'Test reviewer', 'reviewed_on': '2026-01-01',
        'disposition': 'hold', 'rationale': 'Synthetic test; source review remains required.', 'source_reference': 'Fixture Table 3'}
    assert api.post('/literature/reviews', json=review).status_code == 200
    assert api.post('/literature/reviews', json={**review, 'disposition': 'approve'}).status_code == 422
    assert api.get('/literature/records/' + str(result['id'])).json()['payload']['assays'][0]['review_status'] == 'unreviewed'
    assert api.get('/literature/records/' + str(document.id) + '/original').content == JATS
    other = api.post('/projects', json={'name': 'Other'}).json()['id']
    assert api.get('/literature/records/' + str(document.id), params={'project_id': other}).status_code == 404
    assert api.post('/literature/extract', json={'project_id': other, 'document_id': document.id, 'passage_ids': ['P3']}).status_code == 404
    assert api.post('/literature/reports', json={'project_id': other, 'extraction_ids': [result['id']]}).status_code == 404
    with factory() as session:
        stored = session.get(LiteratureRecord, document.id)
        stored.content_blob = b'tampered'
        session.commit()
    assert api.get('/literature/records/' + str(document.id)).status_code == 422
    assert api.post('/literature/reports', json={'extraction_ids': [result['id']]}).status_code == 422


@pytest.mark.parametrize('failure', ['fabricated', 'unselected', 'digest', 'incomplete', 'missing_model', 'connection'])
def test_invalid_or_unavailable_extraction_never_saves_drafts(workspace, monkeypatch, failure):
    api, factory = workspace
    document = source(factory)
    generated = {'assays': [assay()], 'gaps': []}
    if failure == 'fabricated':
        generated['assays'][0]['value']['text'] = '999999'
    if failure == 'unselected':
        generated['assays'][0]['value'] = {'text': 'Human PCSK9', 'passage_id': 'P2'}
    local_model(monkeypatch, generated, digest_changed=failure == 'digest', incomplete=failure == 'incomplete')
    if failure == 'missing_model':
        monkeypatch.setattr(assistant, 'model_status', lambda: {'ready': False, 'message': 'Model missing'})
    if failure == 'connection':
        def failed(s):
            raise httpx.ConnectError('unavailable')
        monkeypatch.setattr(assistant, '_client', failed)
    response = api.post('/literature/extract', json={'document_id': document.id, 'passage_ids': ['P3']})
    assert response.status_code in {422, 503}
    assert api.get('/literature/records', params={'kind': 'extraction'}).json() == []
    assert len(api.get('/literature/records', params={'kind': 'extraction_failure'}).json()) == 1


def test_incompatible_endpoints_and_mixtures_are_flagged():
    data = assay()
    data.update(endpoint='affinity', activity_type='Kd', modality='mixture')
    flags = lab.validate_assay(data)
    assert 'incompatible_with_direct_ppi_ic50_pool' in flags
    assert 'no_molar_pooling_without_defined_molecular_identity' in flags


def test_repeated_or_empty_llm_assays_cannot_pass_quote_checks():
    row = lab.AssayDraft.model_validate(assay())
    with pytest.raises(ValueError, match='Duplicate'):
        lab.check_facts(lab.GeneratedExtraction(assays=[row,row], gaps=[]), sources.parse_jats(JATS)['passages'])
    empty = row.model_copy(update={'compound':None,'value':None,'method':None})
    with pytest.raises(ValueError, match='concrete'):
        lab.check_facts(lab.GeneratedExtraction(assays=[empty], gaps=[]), sources.parse_jats(JATS)['passages'])


def test_literature_dashboard_empty_and_populated_navigation(workspace, monkeypatch, tmp_path):
    api, factory = workspace
    class LocalAPI:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, **kwargs): return api.request(method, path, **kwargs)
    monkeypatch.setattr(httpx, 'Client', LocalAPI)
    monkeypatch.setenv('WORKSPACE_STATE_DIR', str(tmp_path / 'workspaces'))
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'dashboard.py')).run(timeout=20)
    radio = next(r for r in app.sidebar.radio if r.format_func('Literature evidence') in r.options)
    radio.set_value('Literature evidence').run(timeout=20)
    assert not app.exception and not app.error
    assert app.text_input[0].value == ''
    source(factory)
    app.run(timeout=20)
    assert not app.exception and not app.error
    assert any(box.label == 'Evidence passages for local extraction' for box in app.multiselect)
