"""Explicitly selected public sources and local, unreviewed assay extraction."""
import base64
import json
from datetime import date

import streamlit as st

from cvti.dashboard_ui import hero
from cvti.literature import NOTICE


def page(project_id, call):
    hero('Literature evidence', 'Find publications, retain sources and inspect local assay drafts.',
         ['PubMed', 'Europe PMC', 'Human review required'])
    st.info(NOTICE)
    prefix = f'literature_{project_id}_'
    records = call('GET', '/literature/records', params={'project_id': project_id}) or []
    with st.form(prefix + 'search_form'):
        query = st.text_input('Public literature query', value='',
            help='Only this query and the publication dates are sent to PubMed and Europe PMC. Use shared keywords; provider-specific field syntax may differ.')
        start_date = st.date_input('Publication window starts', value=date(2023, 1, 1))
        end_date = st.date_input('Publication window ends', value=date.today())
        limit = st.number_input('Maximum results per provider', min_value=1, max_value=50, value=20)
        submitted = st.form_submit_button('Search and save literature results')
    if submitted:
        st.session_state.pop(prefix + 'result', None)
        result = call('POST', '/literature/search', json={'project_id': project_id, 'query': query, 'limit': limit,
            'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()})
        if result:
            st.rerun()
    searches = [r for r in records if r['kind'] == 'search']
    if searches:
        chosen = st.selectbox('Saved search', searches, format_func=lambda r: f"{r['id']} · {r['title']}")
        search = call('GET', f"/literature/records/{chosen['id']}", params={'project_id': project_id})
        if search:
            data = search['payload']
            st.json(data['providers'])
            st.caption(data['coverage'])
            rows = data['publications']
            if rows:
                index = st.selectbox('Publication', range(len(rows)), format_func=lambda i: rows[i]['title'])
                st.json(rows[index])
                kind = st.selectbox('Source format', ['xml', 'pdf', 'abstract'],
                    help='XML retains repository tables and methods. PDF access may be blocked; abstracts are explicitly limited.')
                if st.button('Retrieve and retain selected source'):
                    st.session_state.pop(prefix + 'result', None)
                    if call('POST', '/literature/retrieve', json={'project_id': project_id,
                        'search_id': chosen['id'], 'publication_index': index, 'format': kind}):
                        st.rerun()
    publications = [r for r in records if r['kind'] == 'publication']
    if publications:
        with st.expander('Upload an accessible source PDF'):
            publication = st.selectbox('PDF publication', publications, format_func=lambda r: f"{r['id']} · {r['title']}")
            upload = st.file_uploader('PDF full text', type=['pdf'])
            reference = st.text_input('PDF source reference or original URL')
            if st.button('Parse and retain uploaded PDF') and upload:
                if call('POST', '/literature/upload-pdf', json={'project_id': project_id,
                    'publication_id': publication['id'], 'pdf_base64': base64.b64encode(upload.getvalue()).decode(),
                    'source_reference': reference}):
                    st.rerun()
    docs = [r for r in records if r['kind'] == 'document']
    if docs:
        chosen = st.selectbox('Retained source document', docs, format_func=lambda r: f"{r['id']} · {r['title']}")
        document = call('GET', f"/literature/records/{chosen['id']}", params={'project_id': project_id})
        if document:
            data = document['payload']
            st.caption(f"Original SHA-256: {document['content_sha256']}")
            st.write(data['limitations'])
            passages = {p['id']: p for p in data['passages']}
            selected = st.multiselect('Evidence passages for local extraction', list(passages), max_selections=16,
                key=prefix + f"passages_{chosen['id']}",
                format_func=lambda i: f"{i} · {passages[i]['locator']} · {passages[i]['text'][:100]}")
            for identifier in selected:
                st.text(f"{identifier} · {passages[identifier]['locator']}\n{passages[identifier]['text']}")
            if st.button('Extract selected evidence with local model'):
                st.session_state.pop(prefix + 'result', None)
                result = call('POST', '/literature/extract', json={'project_id': project_id,
                    'document_id': chosen['id'], 'passage_ids': selected})
                if result:
                    st.rerun()
    else:
        st.caption('No source documents retained. Search and select a publication to begin.')
    extractions = [r for r in records if r['kind'] == 'extraction']
    if extractions:
        chosen = st.selectbox('Saved assay extraction', extractions, format_func=lambda r: f"{r['id']} · {r['title']}")
        detail = call('GET', f"/literature/records/{chosen['id']}", params={'project_id': project_id})
        if detail:
            st.json(detail['payload'])
        with st.expander('Record a human review disposition'):
            with st.form(prefix + 'review'):
                reviewer = st.text_input('Reviewer name')
                reviewed_on = st.date_input('Review date')
                disposition = st.selectbox('Disposition', ['hold', 'exclude', 'needs_information'])
                rationale = st.text_area('Review rationale')
                reference = st.text_input('Reviewed primary source reference')
                if st.form_submit_button('Save review event'):
                    if call('POST', '/literature/reviews', json={'project_id': project_id, 'extraction_id': chosen['id'],
                        'reviewer': reviewer, 'reviewed_on': reviewed_on.isoformat(), 'disposition': disposition,
                        'rationale': rationale, 'source_reference': reference}):
                        st.success('Review event retained; training admission still requires the existing curation process.')
        selected = st.multiselect('Extractions for assessment', [r['id'] for r in extractions])
        if st.button('Save evidence assessment'):
            st.session_state.pop(prefix + 'result', None)
            result = call('POST', '/literature/reports', json={'project_id': project_id, 'extraction_ids': selected})
            if result:
                st.session_state[prefix + 'result'] = result
    if result := st.session_state.get(prefix + 'result'):
        st.download_button('Download assessment Markdown', result['markdown'], 'literature-assessment.md')
        st.download_button('Download evidence JSON', json.dumps(result['report'], indent=2, ensure_ascii=False),
                           'literature-assessment.json', 'application/json')
        st.text(result['markdown'])
