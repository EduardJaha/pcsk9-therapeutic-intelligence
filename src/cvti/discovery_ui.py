"""Connected local discovery pages; no automatic examples or model scoring."""
import json

import altair as alt
import streamlit as st

from cvti.batches import csv_export
from cvti.dashboard_ui import COLORS, hero
from cvti.discovery_chemistry import TRANSFORMS

PAGES = ['Molecule dossier','Endpoint predictions','Target biology','Structure & docking',
         'Assay analysis','SAR & design','Research runs']


def structure_view(atoms, bonds, key='structure'):
    """A self-contained, offline canvas viewer; no CDN or structure transmission."""
    data = json.dumps({'atoms': atoms,'bonds': bonds}).replace('<','\\u003c')
    st.iframe('''<style>
:root{color-scheme:light dark;--viewer-bg:#f3f6f8;--viewer-ink:#243542;--viewer-bond:#738590;--viewer-outline:#fff}
:root[data-appearance="dark"]{color-scheme:dark;--viewer-bg:#1b232c;--viewer-ink:#e8edf2;--viewer-bond:#a6b6c3;--viewer-outline:#35414d}
body{margin:0;font:13px system-ui;color:var(--viewer-ink);background:var(--viewer-bg)}
canvas{display:block;width:100%;height:350px;background:var(--viewer-bg);border-radius:7px;touch-action:none}p{margin:8px}
</style>
<canvas id="mol" aria-label="Interactive molecular conformer"></canvas><p>Drag to rotate · scroll to zoom · generated coordinates in Å</p>
<script>const d='''+data+''';const c=document.getElementById('mol'),ctx=c.getContext('2d');
let rx=.3,ry=.4,zoom=1,drag=null;let a=d.atoms.map(x=>({...x,xyz:[...x.xyz]}));
const center=[0,1,2].map(k=>a.reduce((s,x)=>s+x.xyz[k],0)/Math.max(a.length,1));
a.forEach(x=>x.xyz=x.xyz.map((v,k)=>v-center[k]));let extent=Math.max(3,...a.map(x=>Math.hypot(...x.xyz)));
function draw(){c.width=c.clientWidth*2;c.height=700;ctx.clearRect(0,0,c.width,c.height);
let scale=Math.min(c.width,650)/extent/2.6*zoom;
let p=a.map(x=>{let [u,v,w]=x.xyz;let q=u*Math.cos(ry)+w*Math.sin(ry),z=-u*Math.sin(ry)+w*Math.cos(ry);return {x:c.width/2+q*scale,y:350+(v*Math.cos(rx)-z*Math.sin(rx))*scale,z:v*Math.sin(rx)+z*Math.cos(rx),e:x.element}});
const theme=getComputedStyle(document.documentElement);ctx.lineWidth=5;ctx.strokeStyle=theme.getPropertyValue('--viewer-bond');d.bonds.forEach(b=>{ctx.beginPath();ctx.moveTo(p[b[0]].x,p[b[0]].y);ctx.lineTo(p[b[1]].x,p[b[1]].y);ctx.stroke()});
p.sort((a,b)=>a.z-b.z).forEach(x=>{ctx.fillStyle=({C:'#738590',O:'#e35465',N:'#537bdf',S:'#d9ba3b',F:'#55b895',Cl:'#55b895',H:'#eeeaf5'})[x.e]||'#b48bd0';ctx.beginPath();ctx.arc(x.x,x.y,x.e==='H'?6:11,0,Math.PI*2);ctx.fill();ctx.strokeStyle=theme.getPropertyValue('--viewer-outline');ctx.lineWidth=1;ctx.stroke()})}
c.onpointerdown=e=>{drag=[e.clientX,e.clientY];c.setPointerCapture(e.pointerId)};c.onpointermove=e=>{if(drag){ry+=(e.clientX-drag[0])*.01;rx+=(e.clientY-drag[1])*.01;drag=[e.clientX,e.clientY];draw()}};c.onpointerup=()=>drag=null;c.onwheel=e=>{e.preventDefault();zoom=Math.max(.3,Math.min(4,zoom*Math.exp(-e.deltaY*.001)));draw()};
// The offline srcdoc iframe does not inherit explicit menu appearance. Observe
// only the containing app's scheme; no structures or messages leave the viewer.
let host=null;try{host=parent.document.querySelector('.stApp')}catch{}
const preference=matchMedia('(prefers-color-scheme:dark)');
function syncAppearance(){document.documentElement.dataset.appearance=host?getComputedStyle(host).colorScheme:(preference.matches?'dark':'light');draw()}
if(host)new MutationObserver(syncAppearance).observe(host,{attributes:true,attributeFilter:['class','style']});
preference.addEventListener('change',syncAppearance);new ResizeObserver(draw).observe(c);syncAppearance();</script>''',height=395,alt='Interactive molecular coordinates')


def export_result(result, name):
    st.download_button('Download analysis JSON',json.dumps(result,indent=2),f'{name}.json','application/json',key=f'discovery_export_{name}')


def analyze(call, project_id, kind, payload, save):
    key = f'discovery_{kind}_result'
    st.session_state.pop(key,None)
    result = call('POST','/discovery/analyze',json={'project_id':project_id,'kind':kind,'payload':payload,'save':save})
    if result:
        st.session_state[key] = result
        if result['run_id']: st.success(f"Research run {result['run_id']} saved with input and result checksums.")
    return result


def use_structure(smiles, page):
    st.session_state['discovery_active_smiles'] = smiles
    st.session_state['workspace_nav'] = page
    st.query_params['view'] = page


def dossier_page(project_id,call):
    hero('Molecule dossier','Inspect chemistry, generate a conformer and carry the structure into endpoint predictions or docking.',
         ['Local calculations','Source-aware results','No composite success score'])
    input_column, preview_column = st.columns(2)
    with input_column, st.container(border=True, key='panel_dossier_input'):
        st.subheader('Structure input')
        with st.form('discovery_dossier'):
            smiles = st.text_input('Dossier SMILES',value=st.session_state.get('discovery_active_smiles',''),max_chars=1000,
                                   placeholder='Paste a molecular SMILES string')
            save = st.checkbox('Save this dossier to research history')
            submitted = st.form_submit_button('Build dossier',type='primary')
        st.caption('Calculated properties describe a structure. They do not establish biological activity or clinical benefit.')
        if submitted:
            st.session_state.pop('discovery_conformer_result',None)
            analyze(call,project_id,'dossier',{'smiles':smiles},save)
    saved = st.session_state.get('discovery_dossier_result')
    with preview_column, st.container(border=True, key='panel_dossier_preview'):
        st.subheader('Structure preview')
        if saved:
            st.image(saved['result']['svg'],width='stretch')
            st.code(saved['result']['canonical_smiles'])
        else:
            st.markdown('<div class="studio-empty"><strong>No structure entered</strong>'
                        '<span>Your molecular drawing will appear here.</span></div>', unsafe_allow_html=True)
    if not saved:
        st.info('Enter a molecule to begin. Ring-containing and acyclic small molecules are supported here.')
        return
    result = saved['result']
    left,right = st.columns([1,1.5])
    with left:
        for warning in result['chemistry']['warnings']: st.warning(warning)
        for page in ('Endpoint predictions','Structure & docking','SAR & design'):
            st.button(f'Use this molecule in {page}',on_click=use_structure,args=(result['canonical_smiles'],page),width='stretch')
    with right:
        a,b,c = st.columns(3)
        a.metric('Molecular weight',result['properties']['molecular_weight'])
        b.metric('Calculated logP',result['properties']['logp'])
        c.metric('QED · heuristic',result['properties']['qed'])
        st.dataframe([{'Property':k.replace('_',' '),'Calculated value':v} for k,v in result['properties'].items()],hide_index=True,width='stretch')
    chemistry_tab,conformer_tab,evidence_tab = st.tabs(['Rules & alerts','3D conformer','Provenance & export'])
    with chemistry_tab:
        st.dataframe(result['rules'],hide_index=True,width='stretch')
        if result['alerts']: st.dataframe(result['alerts'],hide_index=True,width='stretch')
        else: st.info('No PAINS/BRENK matches. Absence of a flag does not establish safety.')
        st.caption(result['notice'])
    with conformer_tab:
        if st.button('Generate local 3D conformer'):
            analyze(call,project_id,'conformer',{'smiles':result['canonical_smiles']},save)
        conformer = st.session_state.get('discovery_conformer_result')
        if conformer:
            c = conformer['result']
            structure_view(c['atoms'],c['bonds'])
            st.caption(f"{c['method']} · seed {c['seed']} · optimization converged: {c['optimization_converged']}")
            st.caption(c['notice'])
            st.download_button('Download conformer SDF',c['sdf'],'conformer.sdf','chemical/x-mdl-sdfile')
    with evidence_tab:
        st.json(result['provenance'])
        export_result(saved,'molecule-dossier')


def submit_job(call,project_id,kind,payload):
    st.session_state.pop(f'discovery_{kind}_job',None)
    response = call('POST','/discovery/jobs',json={'project_id':project_id,'kind':kind,'payload':payload})
    if response:
        st.session_state[f'discovery_{kind}_job'] = response['id']
        st.success(f"Run {response['id']} queued. The local cvti worker processes scientific jobs.")


def job_panel(call,project_id,kind):
    identifier = st.session_state.get(f'discovery_{kind}_job')
    if identifier:
        st.button('Refresh run status',key=f'refresh_{kind}')
        run = call('GET',f'/discovery/runs/{identifier}',params={'project_id':project_id})
        if run: render_run(run)


def endpoint_page(project_id,call):
    hero('Endpoint predictions','Select a pinned local model and examine each endpoint in its own units.',
         ['ADMET-AI adapter','No cloud inference','Experimental predictions'])
    caps = call('GET','/discovery/capabilities') or {}
    models = call('GET','/discovery/models') or []
    endpoints = call('GET','/discovery/endpoints') or []
    with st.expander('Local model setup & evidence',expanded=not models):
        st.write('Install the optional environment and create its checkpoint manifest using docs/discovery-workbench.md. Registering preserves an immutable model release; it does not approve scientific use.')
        st.write({'Runtime installed':caps.get('optional_python_present',False),'Manifest present':caps.get('admet_manifest_present',False)})
        if st.button('Register installed experimental model',disabled=not caps.get('admet_manifest_present')):
            if call('POST','/discovery/models/register-local'): st.rerun()
        if models: st.json(models[0]['manifest'])
    st.dataframe([{k:e[k] for k in ('name','category','task','units','species','validation_status')} for e in endpoints],hide_index=True,width='stretch')
    if not models:
        st.info('No registered ADMET release. There are no placeholder predictions.')
        return
    with st.form('discovery_admet'):
        model_id = st.selectbox('ADMET model release',[m['id'] for m in models],format_func=lambda x:f"Release {x} · experimental")
        smiles = st.text_area('Endpoint panel SMILES · one per line',value=st.session_state.get('discovery_active_smiles',''),height=120)
        selected = st.multiselect('Endpoints',[e['id'] for e in endpoints],default=[e['id'] for e in endpoints],
                                  format_func=lambda x:next(e['name'] for e in endpoints if e['id']==x))
        submitted = st.form_submit_button('Queue local endpoint predictions',type='primary')
    if submitted:
        submit_job(call,project_id,'admet',{'model_id':model_id,'smiles':smiles.splitlines(),'endpoints':selected})
    st.caption('Jobs retain their inputs, checkpoint hashes and outputs locally. Predictions are separate from measured assays and PCSK9 activity.')
    job_panel(call,project_id,'admet')


def target_page(project_id,call):
    hero('Target biology','Retrieve public target context and preserve the source response with the analysis.',
         ['Open Targets','Optional RCSB metadata','Explicit public lookup'])
    st.caption('Only the public Ensembl/PDB identifiers are sent to these services. No compound or assay records are uploaded.')
    st.write('PCSK9 reference: ENSG00000169174. Enter the identifier to request a lookup.')
    with st.form('discovery_target'):
        identifier = st.text_input('Human Ensembl gene identifier',max_chars=15)
        pdb = st.text_input('PDB identifier · optional',max_chars=4)
        save = st.checkbox('Save target source snapshot',value=False)
        submitted = st.form_submit_button('Retrieve public target context',type='primary')
    if submitted: analyze(call,project_id,'target',{'ensembl_id':identifier,'pdb_id':pdb or None},save)
    saved = st.session_state.get('discovery_target_result')
    if saved:
        r = saved['result']; target = r['target']
        st.subheader(f"{target['approvedSymbol']} · {target.get('approvedName','')}")
        st.link_button('Open target source',r['target_url'])
        diseases = target.get('associatedDiseases') or {}
        st.caption(f"Showing up to 30 of {diseases.get('count','unknown')} associated diseases. Association is not a compound effect.")
        st.dataframe([{'Disease':x['disease']['name'],'Identifier':x['disease']['id'],'Association score':x['score']} for x in diseases.get('rows',[])],hide_index=True,width='stretch')
        if r['structure_url']:
            st.link_button('Review PDB structure',r['structure_url'])
            with st.expander('Structure metadata'): st.json(r['structure_metadata'])
        st.warning(r['notice'])
        export_result(saved,'target-dossier')


def docking_page(project_id,call):
    hero('Structure & docking','Dock a molecule against an explicitly prepared receptor and a documented pocket.',
         ['Local AutoDock Vina','Reproducible settings','Preserved poses'])
    caps = call('GET','/discovery/capabilities') or {}
    if not caps.get('vina_present'): st.info('Vina is not installed. Configure the local executable using the setup guide.')
    st.caption('Upload a prepared, rigid receptor PDBQT. Review chain selection, mutations, hydrogens, charges, cofactors and protonation before docking. The current tool does not prepare receptors automatically.')
    with st.form('discovery_dock'):
        smiles = st.text_input('Ligand SMILES',value=st.session_state.get('discovery_active_smiles',''),max_chars=1000)
        receptor = st.file_uploader('Prepared receptor PDBQT',type=['pdbqt'])
        target = st.text_input('Target / construct')
        source = st.text_input('Receptor source reference')
        prep = st.text_area('Receptor preparation notes',height=80)
        rationale = st.text_area('Pocket rationale and assay relationship',height=80)
        cols=st.columns(3)
        center=[cols[i].number_input(f'Center {axis} · Å',value=0.,min_value=-10000.,max_value=10000.) for i,axis in enumerate('xyz')]
        size=[cols[i].number_input(f'Box {axis} · Å',value=20.,min_value=5.,max_value=40.) for i,axis in enumerate('xyz')]
        seed=st.number_input('Docking seed',value=2026,min_value=1,max_value=2147483647)
        exhaustive=st.slider('Exhaustiveness',1,16,8)
        submitted=st.form_submit_button('Queue local docking',type='primary')
    if submitted:
        st.session_state.pop('discovery_docking_job',None)
        if not receptor: st.error('Choose a prepared receptor file.')
        elif receptor.size > 2_000_000: st.error('Receptor file must be at most 2 MB.')
        else:
            try: text=receptor.getvalue().decode('utf-8')
            except UnicodeDecodeError: st.error('Receptor must be a UTF-8 PDBQT text file.')
            else: submit_job(call,project_id,'docking',{'smiles':smiles,'receptor_pdbqt':text,'receptor_source':source,
                'target':target,'preparation_notes':prep,'pocket_rationale':rationale,'center':center,'box_size':size,
                'seed':seed,'exhaustiveness':exhaustive,'n_poses':9})
    job_panel(call,project_id,'docking')


def assay_page(project_id,call):
    hero('Assay analysis','Fit concentration-response observations and inspect plate controls without altering raw assay records.',
         ['Explicit concentration units','Preserved replicates','Unreviewed analysis'])
    curve_tab,plate_tab=st.tabs(['Dose-response curve','Plate quality'])
    with curve_tab:
        with st.form('discovery_curve'):
            text=st.text_area('Concentration,response · one pair per line',height=150)
            units=st.selectbox('Concentration units',['nM','uM','mM','M','pM'])
            direction=st.selectbox('Response direction',['increasing','decreasing'])
            source=st.text_input('Curve source reference')
            origin=st.selectbox('Curve data origin',['experimental','synthetic'])
            run_id=st.text_input('Existing assay run ID · optional')
            sample_id=st.text_input('Existing sample ID · optional')
            save=st.checkbox('Save curve analysis to research history')
            submitted=st.form_submit_button('Fit four-parameter curve',type='primary')
        if submitted:
            st.session_state.pop('discovery_curve_result',None)
            try:
                pairs=[list(map(float,line.split(','))) for line in text.splitlines() if line.strip()]
                if any(len(p)!=2 for p in pairs): raise ValueError()
                payload={'concentrations':[p[0] for p in pairs],'responses':[p[1] for p in pairs],'units':units,
                    'direction':direction,'source_reference':source,'data_origin':origin,
                    'assay_run_id':int(run_id) if run_id.strip() else None,'sample_id':int(sample_id) if sample_id.strip() else None}
            except ValueError: st.error('Use two numeric columns per line and integer record IDs when linking records.')
            else: analyze(call,project_id,'curve',payload,save)
        saved=st.session_state.get('discovery_curve_result')
        if saved:
            r=saved['result']
            a,b,c=st.columns(3)
            a.metric(f"Fitted midpoint · {r['units']}",f"{r['midpoint']:.4g}")
            b.metric('Hill slope',f"{r['hill_slope']:.3g}")
            c.metric('R²',f"{r['r_squared']:.3f}")
            for warning in r['warnings']: st.warning(warning)
            points=alt.Chart(alt.Data(values=r['raw'])).mark_circle(size=65).encode(x=alt.X('concentration:Q',scale=alt.Scale(type='log')),y='response:Q',tooltip=['concentration:Q','response:Q','residual:Q'])
            line=alt.Chart(alt.Data(values=r['curve'])).mark_line(color=COLORS[0]).encode(x=alt.X('concentration:Q',scale=alt.Scale(type='log')),y='response:Q')
            st.altair_chart(points+line,width='stretch')
            st.caption(r['notice']);st.json(r['assay_context']);export_result(saved,'dose-response')
    with plate_tab:
        with st.form('discovery_plate'):
            positive=st.text_area('Positive controls · comma separated')
            negative=st.text_area('Negative controls · comma separated')
            save=st.checkbox('Save plate analysis to research history')
            submitted=st.form_submit_button('Calculate plate quality')
        if submitted:
            st.session_state.pop('discovery_plate_result',None)
            try: payload={'positive':[float(x) for x in positive.split(',')],'negative':[float(x) for x in negative.split(',')]}
            except ValueError: st.error('Enter comma-separated numeric controls.')
            else: analyze(call,project_id,'plate',payload,save)
        saved=st.session_state.get('discovery_plate_result')
        if saved:
            st.metric('Z-prime',f"{saved['result']['z_prime']:.3f}")
            st.write(saved['result']['assessment']);st.caption(saved['result']['notice']);export_result(saved,'plate-quality')


def sar_page(project_id,call):
    hero('Structure, activity & design','Search a local library, inspect compatible assay series and enumerate transparent analog hypotheses.',
         ['Similarity screening','Same-assay SAR','Explicit chemical transformations'])
    screen_tab,sar_tab,design_tab=st.tabs(['Similarity screening','Activity cliffs','Analog proposals'])
    with screen_tab:
        with st.form('discovery_screen'):
            query=st.text_input('Reference SMILES',value=st.session_state.get('discovery_active_smiles',''))
            text=st.text_area('Library SMILES · one per line · up to 500',height=160)
            threshold=st.slider('Minimum Tanimoto similarity',0.,1.,.3)
            save=st.checkbox('Save screening analysis')
            submitted=st.form_submit_button('Screen local library',type='primary')
        if submitted: analyze(call,project_id,'screen',{'query':query,'smiles':text.splitlines(),'min_similarity':threshold},save)
        saved=st.session_state.get('discovery_screen_result')
        if saved:
            r=saved['result'];st.dataframe(r['results'],hide_index=True,width='stretch')
            if r['errors']: st.dataframe(r['errors'],hide_index=True,width='stretch')
            st.caption(r['notice']);st.download_button('Download similarity CSV',csv_export(r['results']),'similarity.csv','text/csv');export_result(saved,'similarity-screen')
    with sar_tab:
        st.caption('CSV columns: smiles,value,relation,source_reference,target,endpoint,assay_id,modality,units,data_origin. Use one assay context, exact (=) values and IC50/EC50/Ki/Kd concentration units. Synthetic and experimental rows cannot be mixed.')
        with st.form('discovery_sar'):
            text=st.text_area('Same-assay activity CSV',height=180)
            threshold=st.slider('Pair similarity threshold',0.,1.,.5)
            save=st.checkbox('Save SAR analysis')
            submitted=st.form_submit_button('Analyze activity cliffs')
        if submitted: analyze(call,project_id,'sar',{'csv_content':text,'similarity_threshold':threshold},save)
        saved=st.session_state.get('discovery_sar_result')
        if saved:
            r=saved['result'];st.dataframe(r['pairs'],hide_index=True,width='stretch');st.caption(r['notice']);export_result(saved,'activity-cliffs')
    with design_tab:
        with st.form('discovery_analogs'):
            smiles=st.text_input('Parent molecule SMILES',value=st.session_state.get('discovery_active_smiles',''))
            transforms=st.multiselect('Allowed transformations',list(TRANSFORMS))
            save=st.checkbox('Save analog proposals')
            submitted=st.form_submit_button('Enumerate analog hypotheses')
        if submitted: analyze(call,project_id,'analogs',{'smiles':smiles,'transformations':transforms},save)
        saved=st.session_state.get('discovery_analogs_result')
        if saved:
            r=saved['result'];st.warning(r['notice']);st.dataframe(r['candidates'],hide_index=True,width='stretch')
            st.write('Diversity shortlist');st.code('\n'.join(r['diverse_shortlist']) or 'No products for the selected transformations.')
            st.download_button('Download analog CSV',csv_export(r['candidates']),'analog-proposals.csv','text/csv');export_result(saved,'analog-proposals')


def render_run(run):
    st.subheader(f"Run {run['id']} · {run['kind']} · {run['status']}")
    if run['error']: st.error(run['error'])
    if run['status'] in {'queued','running'}: st.info('Use Refresh run status after the local worker processes this run. Starting or refreshing this page does not rerun calculations.')
    result=run.get('result')
    if result:
        if result.get('notice'): st.caption(result['notice'])
        if run['kind']=='admet':
            st.dataframe([{'Endpoint':r['name'],'Value':r['value'],'Units':r['units'],
                           'Molecule':r['canonical_smiles'],'Type':r['task'],
                           'Applicability':r['applicability'],'Calibration':r['calibration']}
                          for r in result['results']],hide_index=True,width='stretch')
            classes=[r for r in result['results'] if r['task']=='classification']
            if classes:
                chart=alt.Chart(alt.Data(values=classes)).mark_bar().encode(x=alt.X('value:Q',scale=alt.Scale(domain=[0,1]),title='Model output · calibration unknown'),y=alt.Y('name:N',title=None),color='canonical_smiles:N',tooltip=['name:N','canonical_smiles:N','value:Q'])
                st.altair_chart(chart,width='stretch')
            st.download_button('Download endpoint CSV',csv_export(result['results']),f"endpoints-{run['id']}.csv",'text/csv')
        elif run['kind']=='docking':
            st.dataframe([dict(zip(result['energy_columns'],row),pose=i+1) for i,row in enumerate(result['energies_kcal_mol'])],hide_index=True,width='stretch')
            models=[m for m in result['poses_pdbqt'].split('ENDMDL') if 'ATOM' in m]
            if models:
                idx=st.selectbox('Docked pose',list(range(len(models))),format_func=lambda i:f'Pose {i+1}',key=f'pose_{run["id"]}')
                atoms=[]
                for line in models[idx].splitlines():
                    if line.startswith(('ATOM  ','HETATM')):
                        atoms.append({'element':line[12:16].strip()[0],'xyz':[float(line[30:38]),float(line[38:46]),float(line[46:54])]})
                # Show nearby receptor atoms as context, bounded for a local canvas.
                receptor=[]
                p=run['inputs']
                for line in p['receptor_pdbqt'].splitlines():
                    if line.startswith(('ATOM  ','HETATM')):
                        xyz=[float(line[30:38]),float(line[38:46]),float(line[46:54])]
                        if any(sum((x-y)**2 for x,y in zip(xyz,a['xyz']))<=25 for a in atoms):
                            receptor.append({'element':'Receptor','xyz':xyz})
                bonds=[]
                for i,a in enumerate(atoms):
                    for j in range(i):
                        distance=sum((x-y)**2 for x,y in zip(a['xyz'],atoms[j]['xyz']))
                        if .2<distance<3.2: bonds.append([i,j,1])
                structure_view(atoms+receptor[:600],bonds)
                st.caption('Ligand pose with up to 600 nearby receptor atoms (within 5 Å); displayed ligand bonds are distance-based. Inspect the original PDBQT for atom typing and full receptor context.')
            st.download_button('Download all docked poses',result['poses_pdbqt'],f"poses-{run['id']}.pdbqt",'text/plain')
        else:
            with st.expander('Analysis result'): st.json(result)
        export_result(run,f"research-run-{run['id']}")
    with st.expander('Input manifest & provenance'):
        st.json({k:v for k,v in run.items() if k!='result'})


def history_page(project_id,call):
    hero('Research runs','Inspect preserved inputs, model releases, results and failures for this project.',
         ['Checksummed inputs & results','Explicit retry','No assay approval'])
    st.button('Refresh research history')
    runs=call('GET','/discovery/runs',params={'project_id':project_id}) or []
    if not runs:
        st.info('No saved analyses or scientific jobs in this project.')
        return
    st.dataframe(runs,hide_index=True,width='stretch')
    selected=st.selectbox('Research run',[r['id'] for r in runs])
    run=call('GET',f'/discovery/runs/{selected}',params={'project_id':project_id})
    if run:
        render_run(run)
        if run['status'] in {'failed','interrupted'} and st.button('Retry as a new run'):
            created=call('POST',f'/discovery/runs/{selected}/retry',params={'project_id':project_id})
            if created: st.success(f"New run {created['id']} queued; original failure retained.")


def page(name,project_id,call):
    {'Molecule dossier':dossier_page,'Endpoint predictions':endpoint_page,'Target biology':target_page,
     'Structure & docking':docking_page,'Assay analysis':assay_page,'SAR & design':sar_page,'Research runs':history_page}[name](project_id,call)
