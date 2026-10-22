import json
import math
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from cvti.api import create_app
from cvti.assay_analysis import fit_curve, plate_qc
from cvti.config import Settings
from cvti.db import make_engine, session_factory
from cvti.discovery_chemistry import analogs, conformer, dossier, sar
from cvti.discovery_jobs import process_next, recover_jobs
from cvti.discovery_models import interpret_admet, run_engine
from cvti.models import DiscoveryModel, DiscoveryRun
from cvti.registry import json_hash


def select_page(app, page):
    next(radio for radio in app.sidebar.radio if page in radio.options).set_value(page).run(timeout=20)
    assert [radio.value for radio in app.sidebar.radio if radio.value is not None] == [page]
    assert app.query_params["view"] == page


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from cvti import discovery_models, discovery_api
    settings=Settings(_env_file=None,admet_manifest=str(tmp_path/'manifest.json'),discovery_python=str(tmp_path/'missing-python'))
    monkeypatch.setattr(discovery_models,'get_settings',lambda:settings)
    monkeypatch.setattr(discovery_api,'get_settings',lambda:settings)
    url=f'sqlite:///{tmp_path / "research.db"}'
    with TestClient(create_app(url,str(tmp_path/'artifacts'))) as client:
        engine=make_engine(url)
        yield client,session_factory(engine),settings
        engine.dispose()


def model_release(factory):
    manifest={'provider':'admet_ai','package_version':'2.0.1','files':{'model.pt':'a'*64},
              'dependencies':{'admet_ai':'2.0.1'},'status':'experimental'}
    with factory() as session:
        model=DiscoveryModel(manifest_json=manifest,manifest_sha256=json_hash(manifest))
        session.add(model);session.commit();return model.id


def test_dossier_conformer_and_invalid_inputs_do_not_touch_measurements(workspace):
    api,_,_=workspace
    before=api.get('/summary').json()
    response=api.post('/discovery/analyze',json={'kind':'dossier','payload':{'smiles':'CCO'}})
    assert response.status_code==200
    result=response.json()['result']
    assert result['properties']['molecular_weight']==pytest.approx(46.07,.01)
    assert result['provenance']['version'] and result['scaffold']==''
    assert not api.get('/discovery/runs').json()
    assert api.get('/summary').json()==before
    # Old PCSK9 evaluation policy remains intact.
    assert api.post('/molecules/profile',json={'smiles':'CCO'}).status_code==422
    assert api.post('/discovery/analyze',json={'kind':'dossier','payload':{'smiles':'bad'}}).status_code==422
    c=conformer('CCO')
    assert len(c['atoms'])==9 and 'M  END' in c['sdf'] and c['seed']==2026
    assert all(math.isfinite(v) for a in c['atoms'] for v in a['xyz'])
    assert dossier('C[C@H](O)C(=O)O')['canonical_smiles'] != dossier('C[C@@H](O)C(=O)O')['canonical_smiles']


def test_saved_runs_are_project_scoped_and_tamper_is_detected(workspace):
    api,factory,_=workspace
    other=api.post('/projects',json={'name':'Other'}).json()['id']
    saved=api.post('/discovery/analyze',json={'kind':'dossier','save':True,'payload':{'smiles':'CCO'}}).json()
    identifier=saved['run_id']
    assert api.get(f'/discovery/runs/{identifier}',params={'project_id':other}).status_code==404
    assert api.get('/discovery/runs',params={'project_id':other}).json()==[]
    with factory() as session:
        row=session.get(DiscoveryRun,identifier)
        row.result_json={'modified':True};session.commit()
    assert api.get(f'/discovery/runs/{identifier}').status_code==409
    assert api.get('/summary').json()['measurements']==0


def test_curve_units_replicates_and_quality_gates():
    x=np.logspace(-2,4,12)
    y=4+92/(1+(25/x)**1.2)
    nm=fit_curve(x.tolist(),y.tolist(),'nM','increasing')
    um=fit_curve((x/1000).tolist(),y.tolist(),'uM','increasing')
    assert nm['midpoint']==pytest.approx(25,rel=.01)
    assert nm['p_midpoint']==pytest.approx(-math.log10(25e-9),rel=.001)
    assert nm['p_midpoint']==pytest.approx(um['p_midpoint'],rel=.001)
    decreasing=fit_curve(x.tolist(),(100-y).tolist(),'nM','decreasing')
    assert decreasing['midpoint']==pytest.approx(25,rel=.01)
    assert len(fit_curve(np.repeat(x,2).tolist(),np.repeat(y,2).tolist(),'nM','increasing')['raw'])==24
    for badx,bady in [([0]+x[1:].tolist(),y.tolist()),(x.tolist(),[1.]*12),(x.tolist(),[float('nan')]*12)]:
        with pytest.raises(ValueError):fit_curve(badx,bady,'nM','increasing')
    with pytest.raises(ValueError):plate_qc([1,1,1],[1,1,1])
    assert plate_qc([98,96,97,99],[3,5,4,2])['z_prime']>.9


def test_sar_rejects_mixed_context_censoring_and_duplicate_identity():
    header='smiles,value,relation,source_reference,target,endpoint,assay_id,modality,units,data_origin\n'
    rows=['Oc1ccccc1,10,=,source1,PCSK9,IC50,assay1,small_molecule,nM,synthetic',
          'Cc1ccccc1,1000,=,source2,PCSK9,IC50,assay1,small_molecule,nM,synthetic']
    result=sar(header+'\n'.join(rows),0)
    assert result['pairs'][0]['absolute_delta_p_activity']==pytest.approx(2)
    assert result['pairs'][0]['activity_cliff']
    for modified in [rows[1].replace('assay1','assay2'),rows[1].replace('synthetic','experimental'),
                     rows[1].replace(',=,',',>,') ,rows[1].replace('Cc1ccccc1','c1ccccc1O')]:
        with pytest.raises(ValueError):sar(header+rows[0]+'\n'+modified)


def test_screen_and_design_are_transparent_and_non_mutating(workspace):
    api,_,_=workspace
    response=api.post('/discovery/analyze',json={'kind':'screen','payload':{'query':'Oc1ccccc1','smiles':['c1ccccc1O','bad','Oc1ccccc1']}})
    r=response.json()['result']
    assert r['results'][0]['similarity']==1 and len(r['errors'])==2
    designs=analogs('Oc1ccccc1',['Aryl fluorination'])
    assert len(designs['candidates'])==3
    assert len(set(designs['diverse_shortlist']))==3
    assert 'potency' in designs['notice']
    assert api.get('/discovery/runs').json()==[]


def test_admet_jobs_pin_identity_and_manifest_and_keep_failure_history(workspace,monkeypatch):
    from cvti import discovery_jobs
    api,factory,_=workspace
    identifier=model_release(factory)
    raw={'rows':[{'canonical_smiles':'CCO','values':{'hERG':.2}}],'runtime':{'admet_ai':'2.0.1'}}
    monkeypatch.setattr(discovery_jobs,'run_engine',lambda *a,**k:raw)
    payload={'kind':'admet','payload':{'model_id':identifier,'smiles':['CCO'],'endpoints':['hERG']}}
    submitted=api.post('/discovery/jobs',json=payload)
    assert submitted.status_code==200,submitted.text
    job=submitted.json()['id'];assert process_next(factory)==job
    result=api.get(f'/discovery/runs/{job}').json()
    assert result['status']=='completed'
    assert result['result']['results'][0]['confidence'] is None
    assert result['result']['model_manifest_sha256']
    assert api.get('/summary').json()['predictions']==0
    # Invalid numerical model output fails the job rather than becoming a score.
    raw['rows'][0]['values']['hERG']=1.5
    failed=api.post('/discovery/jobs',json=payload).json()['id'];process_next(factory)
    assert api.get(f'/discovery/runs/{failed}').json()['status']=='failed'
    retry=api.post(f'/discovery/runs/{failed}/retry').json()
    assert retry['id']!=failed and retry['inputs']['retry_of']==failed
    assert api.get(f'/discovery/runs/{failed}').json()['status']=='failed'
    other=api.post('/projects',json={'name':'Elsewhere'}).json()['id']
    assert api.post(f'/discovery/runs/{failed}/retry',params={'project_id':other}).status_code==404


def test_admet_missing_runtime_output_mismatch_and_changed_manifest(workspace,monkeypatch):
    from cvti import discovery_jobs
    api,factory,settings=workspace
    with pytest.raises(ValueError,match='missing'):run_engine('admet',{},settings)
    assert api.post('/discovery/models/register-local').status_code==422
    with pytest.raises(ValueError):interpret_admet({'rows':[{'canonical_smiles':'CCN','values':{'hERG':.2}}]},['CCO'],['hERG'])
    for value in [None,float('nan'),float('inf'),True,-.1]:
        with pytest.raises(ValueError):interpret_admet({'rows':[{'canonical_smiles':'CCO','values':{'hERG':value}}]},['CCO'],['hERG'])
    identifier=model_release(factory)
    response=api.post('/discovery/jobs',json={'kind':'admet','payload':{'model_id':identifier,'smiles':['CCO'],'endpoints':['hERG']}})
    with factory() as session:
        model=session.get(DiscoveryModel,identifier);model.manifest_json={'tampered':True};session.commit()
    monkeypatch.setattr(discovery_jobs,'run_engine',lambda *a:pytest.fail('Must verify manifest before loading weights'))
    process_next(factory)
    assert api.get(f'/discovery/runs/{response.json()["id"]}').json()['status']=='failed'


def test_worker_recovers_interrupted_scientific_job_without_reexecution(workspace):
    api,factory,_=workspace
    identifier=model_release(factory)
    job=api.post('/discovery/jobs',json={'kind':'admet','payload':{'model_id':identifier,'smiles':['CCO'],'endpoints':['hERG']}}).json()['id']
    with factory() as session:
        row=session.get(DiscoveryRun,job);row.status='running';session.commit()
    recover_jobs(factory)
    assert process_next(factory) is None
    assert api.get(f'/discovery/runs/{job}').json()['status']=='interrupted'


def test_docking_rejects_bad_grid_and_preserves_engine_result(workspace,monkeypatch):
    from cvti import docking
    api,factory,_=workspace
    atom='ATOM      1  C   ALA A   1       1.000   2.000   3.000  1.00  0.00     0.000 C\n'
    payload={'smiles':'CCO','receptor_pdbqt':atom+atom,'receptor_source':'Synthetic unit test',
             'preparation_notes':'Synthetic coordinates, not a real protein','target':'Test receptor',
             'pocket_rationale':'Test grid','center':[1,2,3],'box_size':[10,10,10]}
    assert api.post('/discovery/jobs',json={'kind':'docking','payload':{**payload,'center':[100,100,100]}}).status_code==422
    assert api.post('/discovery/jobs',json={'kind':'docking','payload':{**payload,'box_size':[0,10,10]}}).status_code==422
    assert api.post('/discovery/jobs',json={'kind':'docking','payload':{**payload,'pocket_rationale':' '}}).status_code==422
    expected={'poses_pdbqt':'MODEL 1\n'+atom+'ENDMDL\n','energies_kcal_mol':[[-3.,0.,0.]],
              'energy_columns':['vina_score_kcal_mol','rmsd_lower_bound_A','rmsd_upper_bound_A'],
              'vina_executable_sha256':'a'*64}
    monkeypatch.setattr(docking,'run_docking',lambda p:expected)
    response=api.post('/discovery/jobs',json={'kind':'docking','payload':payload})
    assert response.status_code==200,response.text
    identifier=response.json()['id'];process_next(factory)
    completed=api.get(f'/discovery/runs/{identifier}').json()
    assert completed['status']=='completed'
    assert completed['inputs']['receptor_pdbqt']==payload['receptor_pdbqt']
    assert completed['result']['vina_executable_sha256']=='a'*64
    assert completed['result']['engine_contract']
    assert api.get('/summary').json()['measurements']==0


def test_curve_rejects_foreign_assay_links_and_requires_attribution(workspace):
    api,_,_=workspace
    payload={'concentrations':[.001,.01,.1,1,10,100],'responses':[5,8,20,52,85,96],
             'units':'uM','direction':'increasing','source_reference':'Synthetic unit test','data_origin':'synthetic'}
    assert api.post('/discovery/analyze',json={'kind':'curve','payload':{**payload,'assay_run_id':9,'sample_id':9}}).status_code==422
    assert api.post('/discovery/analyze',json={'kind':'curve','payload':{**payload,'assay_run_id':9}}).status_code==422
    assert api.post('/discovery/analyze',json={'kind':'curve','payload':{**payload,'source_reference':' '}}).status_code==422
    valid=api.post('/discovery/analyze',json={'kind':'curve','save':True,'payload':payload})
    assert valid.status_code==200,valid.text
    assert valid.json()['result']['assay_context']['data_origin']=='synthetic'
    assert api.get('/summary').json()['measurements']==0


def test_target_snapshot_retains_original_response_and_source_failure(monkeypatch):
    from cvti.target_biology import target_dossier
    def handler(request):
        return httpx.Response(200,json={'data':{'target':{'id':'ENSG00000169174','approvedSymbol':'PCSK9','approvedName':'PCSK9','associatedDiseases':{'count':0,'rows':[]}}}})
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler)))
    result=target_dossier('ENSG00000169174')
    assert result['sources'][0]['sha256'] and 'PCSK9' in result['sources'][0]['response_text']
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(lambda request:httpx.Response(503))))
    with pytest.raises(ValueError,match='unavailable'):target_dossier('ENSG00000169174')


def test_discovery_pages_empty_and_connected_dossier_flow(workspace,monkeypatch,tmp_path):
    from cvti import assistant
    api,_,_=workspace
    monkeypatch.setattr(assistant,'get_settings',lambda:Settings(_env_file=None,assistant_model=''))
    monkeypatch.setenv('WORKSPACE_STATE_DIR',str(tmp_path/'workspaces'))
    class LocalAPI:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def request(self,method,path,**kwargs):return api.request(method,path,**kwargs)
    monkeypatch.setattr(httpx,'Client',LocalAPI)
    monkeypatch.delenv('API_URL',raising=False)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'dashboard.py')).run(timeout=20)
    from cvti.discovery_ui import PAGES
    for page in PAGES:
        select_page(app, page)
        assert not app.exception and not app.error,page
    select_page(app, 'Molecule dossier')
    field=next(x for x in app.text_input if x.label=='Dossier SMILES')
    assert field.value==''
    field.set_value('CCO')
    next(b for b in app.button if b.label=='Build dossier').click().run(timeout=20)
    assert not app.exception and not app.error
    assert app.session_state['discovery_dossier_result']['result']['canonical_smiles']=='CCO'
    next(b for b in app.button if b.label=='Generate local 3D conformer').click().run(timeout=20)
    assert not app.exception and not app.error
    assert len(app.session_state['discovery_conformer_result']['result']['atoms'])==9
    next(b for b in app.button if b.label=='Use this molecule in Structure & docking').click().run(timeout=20)
    assert not app.exception and app.session_state["workspace_nav"]=='Structure & docking'
    assert next(x for x in app.text_input if x.label=='Ligand SMILES').value=='CCO'
    select_page(app, 'Molecule dossier')
    next(x for x in app.text_input if x.label=='Dossier SMILES').set_value('bad')
    next(b for b in app.button if b.label=='Build dossier').click().run(timeout=20)
    assert len(app.error)==1 and 'discovery_dossier_result' not in app.session_state
    assert api.get('/summary').json()['measurements']==0
