"""Streamlit pages for registration, assay records and the candidate workbench."""
import csv
import io
import json

import altair as alt
import streamlit as st

from cvti.batches import csv_export
from cvti.dashboard_ui import hero

MODALITIES = ['small_molecule', 'macrocyclic_peptide', 'peptide', 'other']
ENDPOINTS = ['pcsk9_ldlr_binding', 'pcsk9_expression', 'pcsk9_secretion', 'other_pcsk9']
ENDPOINT_LABELS = {'pcsk9_ldlr_binding': 'PCSK9–LDLR binding', 'pcsk9_expression': 'PCSK9 expression',
                   'pcsk9_secretion': 'PCSK9 secretion', 'other_pcsk9': 'Other PCSK9 endpoint'}


def label(value):
    return ENDPOINT_LABELS.get(value, value.replace('_', ' ').capitalize()) if value else 'Choose explicitly'


def compound_label(row):
    return f"{row['code']} · {row['name'] or row['canonical_smiles']}"


def show_observations(rows):
    if not rows:
        st.caption('No observations recorded for this selection.')
        return
    display = [{**row, 'endpoint': label(row['endpoint']), 'data_origin': label(row['data_origin'])} for row in rows]
    st.dataframe(display, hide_index=True, width='stretch',
                 column_order=['compound_code', 'activity_type', 'relation', 'value_text', 'units',
                               'sample_name', 'run_name', 'endpoint', 'data_origin', 'is_current', 'source_reference', 'id'],
                 column_config={'id': 'Observation ID', 'compound_code': 'Compound', 'sample_name': 'Sample',
                                'run_name': 'Assay run', 'endpoint': 'Endpoint', 'activity_type': 'Readout',
                                'relation': 'Relation', 'value_text': 'Original value', 'units': 'Units',
                                'data_origin': 'Data origin', 'is_current': 'Current record', 'source_reference': 'Source'})


def show_export(project_id, call_file, key):
    if st.button('Prepare registry and assay export', key=key):
        content = call_file(f'/registry/export?project_id={project_id}')
        if content:
            st.download_button('Download registry ZIP', content, f'registry-project-{project_id}.zip', 'application/zip')


def registry_page(project_id, call, call_file):
    hero('Compound registry', 'Keep structures, physical batches and samples linked to their original source.',
         ['Stable compound IDs', 'Explicit registration', 'Validated CSV preview', 'Local storage'])
    result = call('GET', '/registry/compounds', params={'project_id': project_id, 'limit': 1000}) or {'total': 0, 'items': []}
    compounds = result['items']
    st.caption(f"{result['total']} registered compounds in this project. Registration identifies structures; it does not establish activity.")
    if result['total'] > len(compounds):
        st.info('This page lists the first 1,000 compounds. Use Candidate workbench for filtered inspection.')
    compounds_tab, material_tab, import_tab = st.tabs(['Compounds', 'Batches & samples', 'CSV registration'])
    with compounds_tab:
        with st.form(f'register_compound_{project_id}', clear_on_submit=False):
            smiles = st.text_input('Registry SMILES', value='')
            name = st.text_input('Compound name (optional)')
            modality = st.selectbox('Compound modality', [None] + MODALITIES, format_func=label)
            source = st.text_input('Structure source reference', help='Paper, supplier record, design notebook or other attributable identifier.')
            notes = st.text_area('Compound notes')
            if st.form_submit_button('Register compound'):
                registered = call('POST', '/registry/compounds', json={'project_id': project_id, 'smiles': smiles,
                    'name': name, 'modality': modality, 'source_reference': source, 'notes': notes})
                if registered:
                    st.session_state['workspace_notice'] = (f"Registered {registered['code']}" if registered['created'] else
                                                            f"Existing identity: {registered['code']}; original metadata retained")
                    st.session_state.pop('candidate_result', None)
                    st.rerun()
        if compounds:
            selected = st.selectbox('Inspect registered compound', compounds, format_func=compound_label)
            detail = call('GET', f"/registry/compounds/{selected['id']}", params={'project_id': project_id})
            if detail:
                left, right = st.columns([1, 2])
                with left:
                    st.image(detail['svg'])
                with right:
                    st.write(f"{selected['code']} · {selected['canonical_smiles']}")
                    st.dataframe([selected['properties']], hide_index=True, width='stretch',
                                 column_config={'molecular_weight': 'Molecular weight', 'logp': 'Calculated logP',
                                                'tpsa': 'Polar surface area', 'h_bond_donors': 'H-bond donors',
                                                'h_bond_acceptors': 'H-bond acceptors', 'rotatable_bonds': 'Rotatable bonds'})
                    st.caption(f"Source: {selected['source_reference']} · Chemistry: {selected['policy']} · RDKit {selected['rdkit_version']}")
                    for warning in selected['warnings']:
                        st.warning(warning)
                st.write('Recorded assay observations')
                show_observations(detail['observations'])
                st.caption(detail['notice'])
        else:
            st.info('Register a structure or preview a CSV to begin. No examples are added automatically.')
    with material_tab:
        materials = call('GET', '/registry/materials', params={'project_id': project_id}) or {'batches': [], 'samples': []}
        if compounds:
            with st.form(f'new_material_batch_{project_id}'):
                compound = st.selectbox('Batch compound', compounds, format_func=compound_label)
                name = st.text_input('Batch name')
                origin = st.selectbox('Batch data origin', [None, 'research', 'synthetic'], format_func=label)
                source = st.text_input('Batch source reference')
                notes = st.text_input('Batch notes')
                if st.form_submit_button('Record batch'):
                    if call('POST', '/registry/batches', json={'project_id': project_id, 'compound_id': compound['id'],
                            'name': name, 'data_origin': origin, 'source_reference': source, 'notes': notes}):
                        st.rerun()
        else:
            st.info('Register a compound before recording its material batches.')
        if materials['batches']:
            with st.form(f'new_material_sample_{project_id}'):
                batch = st.selectbox('Sample batch', materials['batches'],
                                     format_func=lambda row: f"Batch {row['id']} · {row['name']} · {row['data_origin']}")
                name = st.text_input('Sample name')
                location = st.text_input('Storage location (optional)')
                notes = st.text_input('Sample notes')
                if st.form_submit_button('Record sample'):
                    if call('POST', '/registry/samples', json={'project_id': project_id, 'batch_id': batch['id'],
                            'name': name, 'location': location, 'notes': notes}):
                        st.rerun()
        st.write('Batches')
        st.dataframe(materials['batches'], hide_index=True, width='stretch')
        st.write('Samples')
        st.dataframe(materials['samples'], hide_index=True, width='stretch')
    with import_tab:
        registration_import(project_id, call)
    show_export(project_id, call_file, 'registry_export')


def registration_import(project_id, call):
    st.caption('Map your CSV columns and inspect each row before explicitly registering valid structures. Imports create compound identities only.')
    upload = st.file_uploader('Registration CSV', type=['csv'], max_upload_size=2)
    if upload is not None:
        try:
            text = upload.getvalue().decode('utf-8')
            columns = next(csv.reader(io.StringIO(text.lstrip('\ufeff')), strict=True))
            if not columns or len(set(columns)) != len(columns):
                raise ValueError('Use unique CSV column names')
        except (UnicodeDecodeError, csv.Error, StopIteration, ValueError):
            st.error('Use a UTF-8 CSV with unique column names and valid quoting.')
        else:
            with st.form(f'registration_preview_{project_id}'):
                smiles_column = st.selectbox('CSV SMILES column', columns)
                name_column = st.selectbox('CSV name column', [None] + columns, format_func=lambda x: x or 'Not mapped')
                notes_column = st.selectbox('CSV notes column', [None] + columns, format_func=lambda x: x or 'Not mapped')
                modality = st.selectbox('CSV compound modality', [None] + MODALITIES, format_func=label)
                source = st.text_input('CSV source reference')
                if st.form_submit_button('Preview registration'):
                    st.session_state.pop('registry_preview', None)
                    preview = call('POST', '/registry/imports/preview', json={'project_id': project_id,
                        'csv_content': text, 'smiles_column': smiles_column, 'name_column': name_column,
                        'notes_column': notes_column, 'modality': modality, 'source_reference': source})
                    if preview:
                        st.session_state['registry_preview'] = preview
    history = call('GET', '/registry/imports', params={'project_id': project_id}) or []
    if history:
        saved = st.selectbox('Registration preview history', history,
                             format_func=lambda row: f"Import {row['id']} · {row['status']} · {row['created_at']}")
        if st.button('Open registration preview'):
            st.session_state['registry_preview'] = call('GET', f"/registry/imports/{saved['id']}", params={'project_id': project_id})
    preview = st.session_state.get('registry_preview')
    if preview and preview['project_id'] == project_id:
        st.write(f"Import {preview['id']} · {preview['status']}")
        st.json(preview['counts'])
        rows = [{'row': row['row'], 'status': row['status'], 'input_smiles': row.get('registration', {}).get('smiles', ''),
                 'canonical_smiles': row.get('canonical_smiles', ''), 'message': row.get('message', ''),
                 'warnings': '; '.join(row.get('chemistry', {}).get('warnings', []))} for row in preview['rows']]
        st.dataframe(rows, hide_index=True, width='stretch')
        st.caption(f"Input SHA-256: {preview['input_sha256']} · Plan SHA-256: {preview['plan_sha256']}")
        if preview['status'] == 'preview' and any(row['status'] in {'ready', 'existing'} for row in preview['rows']):
            if st.button('Register valid rows from this preview'):
                committed = call('POST', f"/registry/imports/{preview['id']}/commit", json={
                    'project_id': project_id, 'plan_sha256': preview['plan_sha256']})
                if committed:
                    st.session_state['registry_preview'] = committed
                    st.session_state.pop('candidate_result', None)
                    st.rerun()
        if preview['outcome'] is not None:
            st.write('Registration outcome')
            st.json(preview['outcome'])


def assays_page(project_id, call, call_file):
    hero('Assay records', 'Record the protocol, experimental run and source behind each sample readout.',
         ['PCSK9 endpoints', 'Original units', 'Material provenance', 'Unreviewed records'])
    st.info('These records preserve observations for review. They do not approve assays or add data to model training.')
    protocols = call('GET', '/registry/protocols', params={'project_id': project_id}) or []
    runs = call('GET', '/registry/runs', params={'project_id': project_id}) or []
    materials = call('GET', '/registry/materials', params={'project_id': project_id}) or {'batches': [], 'samples': []}
    with st.expander('Record a protocol', expanded=not protocols):
        with st.form(f'assay_protocol_{project_id}'):
            name = st.text_input('Protocol name')
            st.caption('Target: PCSK9 · CHEMBL2929. Create separate protocols for different endpoints, readouts, units or conditions.')
            endpoint = st.selectbox('Protocol endpoint', [None] + ENDPOINTS, format_func=label)
            activity = st.text_input('Readout type', help='For example IC50, Kd, EC50 or expression. Use the source definition.')
            units = st.text_input('Protocol units')
            modality = st.selectbox('Protocol modality', [None] + MODALITIES, format_func=label)
            species = st.text_input('Assay species')
            constructs = st.text_input('Protein or cell constructs')
            method = st.text_area('Assay method')
            conditions = st.text_area('Assay conditions')
            source = st.text_input('Protocol source reference')
            if st.form_submit_button('Record protocol'):
                if call('POST', '/registry/protocols', json={'project_id': project_id, 'name': name,
                    'endpoint': endpoint, 'activity_type': activity, 'units': units, 'modality': modality,
                    'species': species, 'constructs': constructs, 'method': method,
                    'conditions': conditions, 'source_reference': source}):
                    st.rerun()
    if protocols:
        with st.expander('Record an assay run', expanded=not runs):
            with st.form(f'assay_run_{project_id}'):
                protocol = st.selectbox('Run protocol', protocols, format_func=lambda row: f"{row['name']} · {row['endpoint']} · {row['activity_type']} ({row['units']})")
                name = st.text_input('Run name')
                performed = st.date_input('Experiment date', value=None)
                operator = st.text_input('Experiment operator')
                origin = st.selectbox('Run data origin', [None, 'research', 'synthetic'], format_func=label)
                source = st.text_input('Run source reference')
                notes = st.text_input('Run notes')
                if st.form_submit_button('Record run'):
                    if call('POST', '/registry/runs', json={'project_id': project_id, 'protocol_id': protocol['id'],
                        'name': name, 'performed_on': performed.isoformat() if performed else None,
                        'operator': operator, 'data_origin': origin, 'source_reference': source, 'notes': notes}):
                        st.rerun()
    if runs:
        selected = st.selectbox('Inspect assay run', runs, format_func=lambda row: f"Run {row['id']} · {row['name']} · {row['data_origin']}")
        protocol = next(row for row in protocols if row['id'] == selected['protocol_id'])
        result = call('GET', '/registry/observations', params={'project_id': project_id, 'run_id': selected['id']})
        with st.expander('Protocol and run provenance'):
            st.json({'protocol': protocol, 'run': selected})
        batch_by_id = {row['id']: row for row in materials['batches']}
        compounds = (call('GET', '/registry/compounds', params={'project_id': project_id, 'limit': 1000}) or {'items': []})['items']
        modality_by_id = {row['id']: row['modality'] for row in compounds}
        samples = [row for row in materials['samples'] if batch_by_id[row['batch_id']]['data_origin'] == selected['data_origin']
                   and modality_by_id.get(batch_by_id[row['batch_id']]['compound_id']) == protocol['modality']]
        if samples:
            with st.form(f'assay_observation_{project_id}_{selected["id"]}'):
                st.caption(f"{label(protocol['endpoint'])} · {protocol['activity_type']} · units: {protocol['units']}")
                sample = st.selectbox('Observation sample', samples, format_func=lambda row: f"Sample {row['id']} · {row['name']} · batch {row['batch_id']}")
                identifier = st.text_input('Source result identifier', help='A unique source row or replicate ID within this run.')
                relation = st.selectbox('Measurement relation', ['=', '<', '<=', '>', '>='])
                value = st.text_input('Original numeric value')
                source = st.text_input('Observation source reference')
                prior = [row['id'] for row in (result or {}).get('items', []) if row['is_current']]
                correction = st.selectbox('Earlier observation to correct (optional)', [None] + prior,
                                          format_func=lambda value: 'New observation' if value is None else f'Observation {value}')
                notes = st.text_input('Observation notes or correction rationale')
                if st.form_submit_button('Record observation'):
                    if call('POST', '/registry/observations', json={'project_id': project_id, 'run_id': selected['id'],
                        'sample_id': sample['id'], 'source_record_id': identifier, 'value_text': value,
                        'relation': relation, 'units': protocol['units'], 'source_reference': source,
                        'supersedes_id': correction, 'notes': notes}):
                        st.rerun()
        else:
            st.info('Record a sample whose modality and research/synthetic origin match this run to add observations.')
        if result:
            show_observations(result['items'])
            st.download_button('Download run observations CSV', csv_export(result['items']),
                               f"assay-run-{selected['id']}.csv", 'text/csv')
    elif not protocols:
        st.caption('Start with a protocol. No assay data are preloaded.')
    show_export(project_id, call_file, 'assay_export')


def candidates_page(project_id, model_id, runs, call):
    hero('Candidate workbench', 'Filter registered compounds, retain useful searches and inspect selected model hypotheses.',
         ['Calculated properties', 'Saved views', 'Explicit model selection', 'Read-only scoring'])
    saved = call('GET', '/registry/views', params={'project_id': project_id}) or []
    if saved:
        view = st.selectbox('Saved candidate view', saved, format_func=lambda row: row['name'])
        if st.button('Run saved candidate view'):
            st.session_state.pop('candidate_scores', None)
            st.session_state['candidate_result'] = call('POST', f"/registry/views/{view['id']}/run", json={'project_id': project_id})
    with st.expander('Filter candidates', expanded=False), st.form(f'candidate_filters_{project_id}'):
        name = st.text_input('Name or notes contain')
        modality = st.selectbox('Candidate modality', [None] + MODALITIES, format_func=lambda x: label(x) if x else 'All modalities')
        query = st.text_input('Candidate structure query', value='')
        mode = st.selectbox('Candidate structure match', ['none', 'exact', 'substructure', 'similarity'],
                            format_func=lambda value: 'Any structure' if value == 'none' else label(value))
        similarity = st.slider('Candidate minimum similarity', 0.0, 1.0, 0.5, 0.05)
        c1, c2 = st.columns(2)
        with c1:
            min_mw = st.number_input('Minimum molecular weight (optional)', min_value=0.0, value=None)
            min_logp = st.number_input('Minimum calculated logP (optional)', value=None)
        with c2:
            max_mw = st.number_input('Maximum molecular weight (optional)', min_value=0.0, value=None)
            max_logp = st.number_input('Maximum calculated logP (optional)', value=None)
        if st.form_submit_button('Apply candidate filters'):
            st.session_state.pop('candidate_scores', None)
            st.session_state['candidate_result'] = call('POST', '/registry/workbench/search', json={'project_id': project_id,
                'criteria': {'name': name, 'modality': modality, 'query_smiles': query, 'match_mode': mode,
                             'min_similarity': similarity, 'min_mw': min_mw, 'max_mw': max_mw,
                             'min_logp': min_logp, 'max_logp': max_logp}})
    if 'candidate_result' not in st.session_state:
        st.session_state['candidate_result'] = call('POST', '/registry/workbench/search', json={'project_id': project_id})
    result = st.session_state.get('candidate_result')
    if not result or result['project_id'] != project_id:
        return
    st.caption(f"Last applied search: {result['total_hits']} matches · showing {result['returned']} (maximum {result['criteria']['limit']})")
    rows = [{key: row[key] for key in ['id', 'code', 'name', 'canonical_smiles', 'modality', 'molecular_weight',
                                      'logp', 'tpsa', 'similarity', 'source_reference']} for row in result['items']]
    st.dataframe([{**row, 'modality': label(row['modality'])} for row in rows], hide_index=True, width='stretch',
                 column_config={'id': None, 'code': 'Compound', 'name': 'Name', 'canonical_smiles': 'SMILES',
                                'modality': 'Modality', 'molecular_weight': 'Molecular weight',
                                'logp': 'Calculated logP', 'tpsa': 'Polar surface area',
                                'similarity': st.column_config.NumberColumn('Similarity', format='%.3f'),
                                'source_reference': 'Structure source'})
    st.caption(result['notice'])
    if not rows:
        st.info('Register compounds or adjust the filters to see candidates.')
    if len(rows) >= 2:
        chart = alt.Chart(alt.Data(values=rows)).mark_circle(size=90).encode(
            x=alt.X('molecular_weight:Q', title='Calculated molecular weight'),
            y=alt.Y('logp:Q', title='Calculated logP'), color='modality:N',
            tooltip=[alt.Tooltip('code:N', title='Compound'), alt.Tooltip('name:N', title='Name'),
                     alt.Tooltip('canonical_smiles:N', title='SMILES'),
                     alt.Tooltip('molecular_weight:Q', title='Molecular weight'),
                     alt.Tooltip('logp:Q', title='Calculated logP')]).properties(height=300)
        st.altair_chart(chart, width='stretch')
    st.download_button('Download displayed candidates CSV', csv_export(rows), 'candidates.csv', 'text/csv')
    if rows:
        with st.expander('Inspect candidate source and assay records'):
            inspected = st.selectbox('Candidate evidence', result['items'], format_func=compound_label)
            detail = call('GET', f"/registry/compounds/{inspected['id']}", params={'project_id': project_id})
            if detail:
                st.image(detail['svg'], width=300)
                st.caption(f"Structure source: {inspected['source_reference']}")
                show_observations(detail['observations'])
                st.caption(detail['notice'])
    with st.form(f'save_candidate_view_{project_id}'):
        name = st.text_input('New candidate view name')
        if st.form_submit_button('Save applied candidate view'):
            if call('POST', '/registry/views', json={'project_id': project_id, 'name': name, 'criteria': result['criteria']}):
                st.rerun()
    st.subheader('Preview selected model hypotheses')
    selected_model = next((run for run in runs if run['id'] == model_id), None)
    if not selected_model:
        st.caption('Select a scoring model in the sidebar to preview hypotheses for chosen candidates.')
        return
    st.caption(f"Experiment {model_id} · {selected_model['model_kind']} · {selected_model['data_source']}. Previews do not save predictions.")
    selected_ids = st.multiselect('Candidates to score (up to 50)', [row['id'] for row in rows],
                                 format_func=lambda value: next(f"{r['code']} · {r['name']}" for r in rows if r['id'] == value),
                                 max_selections=50)
    if st.button('Preview candidate scores', disabled=not selected_ids):
        st.session_state.pop('candidate_scores', None)
        st.session_state['candidate_scores'] = call('POST', '/registry/workbench/score', json={
            'project_id': project_id, 'experiment_id': model_id, 'compound_ids': selected_ids})
    scores = st.session_state.get('candidate_scores')
    if scores and scores['project_id'] == project_id and scores['experiment_id'] == model_id:
        scored = [{'compound_id': row['compound_id'], 'status': row['status'],
                   'exploratory_score': row.get('prediction', {}).get('probability_exploratory_activity'),
                   'message': row.get('message', ''), 'experiment_id': scores['experiment_id'],
                   'dataset_version_id': scores['dataset_version_id']} for row in scores['items']]
        st.dataframe(scored, hide_index=True, width='stretch')
        with st.expander('Model evidence and limitations'):
            st.json(scores['model_card'])
        st.download_button('Download candidate score provenance JSON', json.dumps(scores, indent=2), 'candidate-scores.json', 'application/json')
