import hashlib
import socket
from pathlib import Path
import pytest
from pypdf import PdfReader
from paperguard.pdf import validate_pdf,inspect_pdf,extract_first,merge,public_target,download_pdf
from paperguard.models import AuditTask,Reference
from conftest import make_pdf

META={'title':'A reliable test paper','author':'Smith, Alice and Jones, Bob','doi':'10.1234/test-alpha'}

@pytest.mark.parametrize('content',[b'<html>Error</html>',b'%PDF-1.7 broken',b''])
def test_invalid_pdf(tmp_path,content):
    source = tmp_path/'invalid.pdf';source.write_bytes(content)
    with pytest.raises(Exception): validate_pdf(source)

def test_matching_and_first_page_preservation(tmp_path):
    source = make_pdf(tmp_path/'good.pdf')
    assert inspect_pdf(source,META)[0]=='confirmed'
    extract_first(source,tmp_path/'first.pdf')
    original,first = PdfReader(source),PdfReader(tmp_path/'first.pdf')
    assert len(first.pages)==1
    assert first.pages[0].mediabox==original.pages[0].mediabox
    assert first.pages[0].extract_text()==original.pages[0].extract_text()
    assert first.pages[0].get_contents().get_data()==original.pages[0].get_contents().get_data()

def test_wrong_pdf_excluded(tmp_path):
    source = make_pdf(tmp_path/'wrong.pdf','Unrelated title\n10.9999/wrong')
    assert inspect_pdf(source,META)[0]=='mismatch'

def test_probable_needs_confirmation_and_mixed_sizes(tmp_path):
    a = make_pdf(tmp_path/'a.pdf',META['title'],((612,792),(500,700)))
    b = make_pdf(tmp_path/'b.pdf',sizes=((420,600),))
    assert inspect_pdf(a,META)[0]=='probable'
    refs=[]
    for name,path,status in [('a',a,'probable'),('b',b,'confirmed')]:
        refs.append(Reference(citation_key=name,entry_type='article',raw_bibtex='',input_metadata=META,source_file='',source_line=1,pdf_path=str(path),pdf_match_status=status,pdf_evidence={'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
    task=AuditTask(project_path='.',output_path=str(tmp_path),references=refs)
    assert merge(task)==1
    refs[0].pdf_approved=True
    assert merge(task)==2
    result=PdfReader(tmp_path/'Reference_First_Pages.pdf')
    assert [tuple(p.mediabox) for p in result.pages]==[(0,0,612,792),(0,0,420,600)]
    assert all('SECOND PAGE' not in p.extract_text() for p in result.pages)

@pytest.mark.parametrize('url',['http://example.org/a.pdf','file:///etc/passwd','https://user:pass@example.org/a','https://example.org:8443/a'])
def test_bad_url(url):
    with pytest.raises(ValueError): public_target(url)

@pytest.mark.parametrize('address',['127.0.0.1','10.1.1.1','169.254.169.254','::1','fc00::1'])
def test_ssrf_addresses(monkeypatch,address):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',(address,443))])
    with pytest.raises(ValueError): public_target('https://example.org/a.pdf')

def test_html_download_rejected(monkeypatch,tmp_path,settings):
    import paperguard.pdf as pdf
    class Response:
        status=200
        def getheader(self,key,default=None):return 'application/pdf' if key=='Content-Type' else default
        def read(self,size):
            if getattr(self,'done',False): return b''
            self.done=True;return b'<html>not a PDF</html>'
    class Connection:
        def __init__(self,*args):pass
        def request(self,*args,**kwargs):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(pdf,'public_target',lambda url:(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(url),'93.184.216.34'))
    monkeypatch.setattr(pdf,'PinnedHTTPS',Connection)
    with pytest.raises(ValueError,match='not a PDF'):download_pdf('https://example.org/a.pdf',tmp_path,settings)
    assert not list(tmp_path.glob('*.part')) and not list(tmp_path.glob('*.pdf'))
