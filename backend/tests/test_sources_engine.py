import json
from pathlib import Path
import httpx
import pytest
from openpyxl import load_workbook
from paperguard.sources import Sources
from paperguard.engine import Engine
from paperguard.reporting import export
from conftest import make_pdf

def test_real_adapter_shapes_cache(settings,store,monkeypatch):
    import paperguard.sources as module
    monkeypatch.setattr(module.time,'sleep',lambda x:None)
    calls=[]
    def handle(request):
        calls.append(str(request.url))
        if request.url.host=='api.crossref.org':
            return httpx.Response(200,json={'message':{'DOI':'10.1/test','title':['Title'],'author':[{'family':'Smith','given':'Alice'}],'published':{'date-parts':[[2020]]}}})
        return httpx.Response(200,json={'id':'https://openalex.org/W1','title':'Title','publication_year':2020,'doi':'https://doi.org/10.1/test','authorships':[{'author':{'display_name':'Alice Smith'}}],'locations':[{'is_oa':True,'pdf_url':'https://example.org/a.pdf','license':'cc-by'}]})
    sources=Sources(settings,store,httpx.Client(transport=httpx.MockTransport(handle)))
    for source in ['crossref','openalex']:
        records,q=sources.query(source,'doi','10.1/test')
        assert records[0].normalized_metadata['title']=='Title'
        assert records[0].retrieved_at and records[0].source_record_id
        _,cached=sources.query(source,'doi','10.1/test')
        assert cached['cached'] and cached['retrieved_at']==q['retrieved_at']
    assert len(calls)==2

def test_arxiv_adapter(settings,store,monkeypatch):
    import paperguard.sources as module
    monkeypatch.setattr(module.time,'sleep',lambda x:None)
    xml='<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/1234.5678</id><title>Fixture</title><published>2020-01-01</published><author><name>Alice Smith</name></author><summary>Abstract</summary><link title="pdf" href="http://arxiv.org/pdf/1234.5678"/></entry></feed>'
    s=Sources(settings,store,httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=xml))))
    records,q=s.query('arxiv','title','Fixture')
    assert records[0].normalized_metadata['oa_locations'][0]['url'].startswith('https:')

def test_rate_limits_and_errors_not_cached(settings,store,monkeypatch):
    import paperguard.sources as module
    monkeypatch.setattr(module.time,'sleep',lambda x:None)
    calls=[]
    def handle(request):
        calls.append(1)
        return httpx.Response(429,headers={'Retry-After':'1'})
    s=Sources(settings,store,httpx.Client(transport=httpx.MockTransport(handle)))
    records,q=s.query('crossref','doi','10.1234/missing')
    assert records==[] and q['status']=='error' and len(calls)==3

def test_offline_end_to_end_reports_and_upload(project,settings,store,tmp_path):
    engine=Engine(settings,store)
    original=(project/'refs.bib').read_bytes()
    task=engine.create(project,offline=True)
    task=engine.run(task.task_id)
    assert task.status=='partial' and task.progress==100
    assert all(r.verification_status.value=='unverified' for r in task.references)
    output=Path(task.output_path)
    assert (output/'Reference_Verification_Report.html').exists()
    assert (output/'Corrected_References.bib').exists()
    book=load_workbook(output/'Reference_Metadata.xlsx')
    assert book.sheetnames==['Summary','References','Metadata_Differences','Citation_Issues','Semantic_Audit','PDF_Status']
    source=make_pdf(tmp_path/'uploaded.pdf')
    task=engine.upload(task.task_id,task.references[0].id,source)
    assert task.merged_pages==1
    assert (output/'Reference_First_Pages.pdf').exists()
    assert (project/'refs.bib').read_bytes()==original
    assert json.loads((output/'Verification_Records.json').read_text(encoding='utf-8'))['summary']['merged_pages']==1

def test_interruption_resume_skips_completed(project,settings,store,candidate):
    class Stub:
        def __init__(self):self.calls=[];self.interrupt=True
        def search(self,metadata):
            self.calls.append(metadata.get('title'))
            if len(self.calls)==2 and self.interrupt: raise KeyboardInterrupt()
            return [candidate.model_copy(deep=True)],[{'status':'ok'}]
    source=Stub();engine=Engine(settings,store,source)
    task=engine.create(project,collect=False)
    with pytest.raises(KeyboardInterrupt):engine.run(task.task_id)
    assert store.get(task.task_id).references[0].processed
    source.interrupt=False
    finished=engine.run(task.task_id)
    assert all(r.processed for r in finished.references)
    assert source.calls.count('A reliable test paper')==1

def test_cancel_partial_success(project,settings,store,candidate):
    class Stub:
        def search(self,metadata):
            store.cancel(task.task_id)
            return [candidate.model_copy(deep=True)],[{'status':'ok'}]
    engine=Engine(settings,store,Stub());task=engine.create(project,collect=False)
    task=engine.run(task.task_id)
    assert task.status=='cancelled'
    assert sum(r.processed for r in task.references)==1
    assert (Path(task.output_path)/'Verification_Records.json').exists()

def test_input_changes_block_resume(project,settings,store):
    engine=Engine(settings,store);task=engine.create(project,offline=True)
    with (project/'refs.bib').open('a') as f:f.write('\n%changed')
    task=engine.run(task.task_id)
    assert task.status=='failed' and 'changed' in task.error_summary[0]

def test_export_escapes_html_and_spreadsheet(project,settings,store):
    engine=Engine(settings,store);task=engine.create(project,offline=True)
    task.references[0].input_metadata['title']='<script>alert(1)</script>'
    task.references[0].citation_key='=WEBSERVICE("x")'
    export(task)
    output=Path(task.output_path)
    assert '<script>alert(1)</script>' not in (output/'Reference_Verification_Report.html').read_text(encoding='utf-8')
    book=load_workbook(output/'Reference_Metadata.xlsx')
    assert book['References']['A2'].data_type=='s'
    assert book['References']['A2'].value.startswith("'")
