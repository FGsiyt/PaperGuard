import io
import time
import zipfile
import pytest
from fastapi.testclient import TestClient
from paperguard.api import create_app,extract_zip
from paperguard.semantic import audit_semantic
from paperguard.engine import Engine

def test_api_import_task_reports_and_csrf(settings,project):
    app=create_app(settings);client=TestClient(app)
    assert client.get('/api/tasks').status_code==200
    assert client.post('/api/tasks',json={'project_path':str(project)}).status_code==403
    headers={'X-PaperGuard-Token':app.state.token}
    assert client.post('/api/tasks',headers={**headers,'origin':'https://evil.test'},json={'project_path':str(project)}).status_code==403
    response=client.post('/api/tasks',headers=headers,json={'project_path':str(project),'offline':True})
    assert response.status_code==200
    task_id=response.json()['task_id']
    for _ in range(100):
        task=client.get('/api/tasks/'+task_id).json()
        if task['status'] not in {'queued','running'}:break
        time.sleep(.05)
    assert task['status']=='partial'
    files=client.get('/api/tasks/'+task_id+'/files').json()
    assert any(f['name']=='Reference_Metadata.xlsx' for f in files)
    assert client.get('/api/tasks/'+task_id+'/files/Verification_Records.json').status_code==200
    assert client.get('/api/tasks',headers={'host':'evil.test'}).status_code==403
    assert client.get('/api/settings').json()['llm_key_configured'] is False

@pytest.mark.parametrize('name',['../escape.tex','/absolute.tex','C:/evil.tex','folder/../../evil.tex'])
def test_zip_traversal(tmp_path,name):
    source=tmp_path/'bad.zip'
    with zipfile.ZipFile(source,'w') as f:f.writestr(name,'bad')
    with pytest.raises(ValueError):extract_zip(source,tmp_path/'out')

def test_semantic_disabled_no_network(project,settings,store):
    engine=Engine(settings,store);task=engine.create(project,offline=True)
    r=task.references[0]
    audit_semantic(r,settings,False)
    assert r.semantic_audit_status=='not_checked' and r.semantic_results
    audit_semantic(r,settings,True)
    assert r.semantic_audit_status=='not_checked'
    settings.llm_base='http://127.0.0.1:12345/v1';settings.llm_model='test'
    audit_semantic(r,settings,True)
    assert r.semantic_audit_status=='insufficient_evidence'
