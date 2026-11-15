import hashlib
import httpx
import pytest
from paperguard.models import AuditTask,Reference
from paperguard.pdf import merge
from paperguard.engine import Engine
from paperguard.semantic import audit_semantic
from conftest import make_pdf

def test_merge_keeps_link_source_readers_open(monkeypatch,tmp_path):
    import paperguard.pdf as module
    readers=[]
    real_reader=module.PdfReader
    real_write=module.PdfWriter.write
    def track(path,*args,**kwargs):
        reader=real_reader(path,*args,**kwargs)
        if 'First_Pages' in str(path):readers.append(reader)
        return reader
    def guarded_write(writer,stream,*args,**kwargs):
        # pypdf resolves named destination links lazily at write time.
        assert all(not r.stream.closed for r in readers)
        return real_write(writer,stream,*args,**kwargs)
    monkeypatch.setattr(module,'PdfReader',track)
    monkeypatch.setattr(module.PdfWriter,'write',guarded_write)
    path=make_pdf(tmp_path/'source.pdf')
    ref=Reference(citation_key='a',entry_type='article',raw_bibtex='',input_metadata={},source_file='',source_line=1,pdf_path=str(path),pdf_match_status='confirmed',pdf_evidence={'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    task=AuditTask(project_path='.',output_path=str(tmp_path),references=[ref])
    assert merge(task)==1
    assert readers and all(r.stream.closed for r in readers)

@pytest.mark.parametrize('valid',[True,False])
def test_semantic_validates_verbatim_evidence(monkeypatch,project,settings,store,tmp_path,valid):
    import paperguard.semantic as module
    text='Residual learning eases the training of deep neural networks. This is a synthetic fixture paragraph used only for validating evidence attribution.'
    path=make_pdf(tmp_path/'evidence.pdf',text,sizes=((612,792),))
    task=Engine(settings,store).create(project,offline=True)
    ref=task.references[0];ref.pdf_path=str(path);ref.pdf_match_status='confirmed'
    settings.llm_base='http://localhost:11434/v1';settings.llm_model='fixture-model'
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            import json
            assert url.endswith('/v1/chat/completions')
            assert 'synthetic fixture paragraph' in kwargs['json']['messages'][1]['content']
            answer={'label':'supported','explanation':'fixture assertion','confidence':.9,'evidence_ids':['1'],'quotes':['Residual learning eases the training of deep neural networks.' if valid else 'The model invented this unsupported sentence.']}
            return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':json.dumps(answer)}}]})
    monkeypatch.setattr(module.httpx,'Client',Client)
    audit_semantic(ref,settings,True)
    assert ref.semantic_audit_status==('supported' if valid else 'insufficient_evidence')
    assert ref.semantic_results[0]['evidence'][0]['page']==1
