import pytest
from fastapi.testclient import TestClient
from paperguard.api import create_app
from paperguard.engine import Engine
from paperguard.verification import classify

META={'title':'A reliable test paper','author':'Smith, Alice and Jones, Bob','year':'2020','doi':'10.1234/test-alpha'}

def test_cross_source_missing_doi_is_agreement(candidate):
    other=candidate.model_copy(deep=True)
    other.source_name='fixture-arxiv'
    other.normalized_metadata['doi']=''
    assert classify(META,[candidate,other],[{'status':'ok'}])[0].value=='verified'

def test_same_doi_conflicting_source_title_requires_review(candidate):
    other=candidate.model_copy(deep=True)
    other.source_name='fixture-openalex'
    other.normalized_metadata['title']='An unrelated source title'
    assert classify(META,[candidate,other],[{'status':'ok'}])[0].value=='manual_review'

@pytest.mark.parametrize('action',['retry','approve'])
def test_unknown_reference_returns_404(settings,project,action):
    app=create_app(settings)
    engine=app.state.engine
    task=engine.create(project,offline=True)
    task=engine.run(task.task_id)
    client=TestClient(app)
    headers={'X-PaperGuard-Token':app.state.token}
    suffix='/retry/not-a-reference' if action=='retry' else '/approve/not-a-reference/correction'
    response=client.post('/api/tasks/'+task.task_id+suffix,headers=headers)
    assert response.status_code==404
    assert response.json()['detail']=='Reference not found'
