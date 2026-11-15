import hashlib
import http.client
import ipaddress
import os
import re
import shutil
import socket
import ssl
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from pypdf import PdfReader, PdfWriter
from .normalization import norm, doi, surnames
from .models import now

def safe_name(value):
    return re.sub(r'[^A-Za-z0-9_-]','_',value)[:80] or 'reference'

def public_target(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in {None,443}:
        raise ValueError('Only public HTTPS on port 443 is allowed')
    addresses = {row[4][0] for row in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('Private, loopback or reserved download destination blocked')
    return p,sorted(addresses)[0]

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip,timeout):
        super().__init__(host,timeout=timeout,context=ssl.create_default_context())
        self.ip = ip
    def connect(self):
        # Pin the checked IP; DNS cannot rebind between validation and connection.
        sock = socket.create_connection((self.ip,443),self.timeout)
        self.sock = self._context.wrap_socket(sock,server_hostname=self.host)

def validate_pdf(path,max_bytes=50*1024*1024):
    path = Path(path)
    if not 8 <= path.stat().st_size <= max_bytes:
        raise ValueError('PDF size is invalid or exceeds limit')
    with path.open('rb') as f:
        if not f.read(1024).lstrip().startswith(b'%PDF-'):
            raise ValueError('Response is not a PDF (possibly an HTML error page)')
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('Encrypted PDF requires a password')
    if not len(reader.pages) or len(reader.pages) > 10000:
        raise ValueError('PDF page count is invalid')
    return reader

def download_pdf(url,directory,settings):
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    fd,temp = tempfile.mkstemp(suffix='.part',dir=directory)
    os.close(fd)
    try:
        original_url = url
        for redirect in range(6):
            parsed,ip = public_target(url)
            conn = PinnedHTTPS(parsed.hostname,ip,min(settings.timeout,30))
            try:
                conn.request('GET',parsed.path+('?' + parsed.query if parsed.query else ''),headers={'User-Agent':'PaperGuard/1.0','Accept':'application/pdf'})
                response = conn.getresponse()
                if response.status in {301,302,303,307,308}:
                    target = response.getheader('Location')
                    if not target:
                        raise ValueError('Redirect has no destination')
                    url = urljoin(url,target)
                    continue
                if response.status != 200:
                    raise ValueError('PDF HTTP status '+str(response.status))
                content_type = response.getheader('Content-Type','')
                length = response.getheader('Content-Length')
                if length and int(length) > settings.max_pdf_bytes:
                    raise ValueError('PDF exceeds size limit')
                size = 0
                with open(temp,'wb') as output:
                    while chunk := response.read(65536):
                        size += len(chunk)
                        if size > settings.max_pdf_bytes:
                            raise ValueError('PDF exceeds size limit')
                        output.write(chunk)
                reader = validate_pdf(temp,settings.max_pdf_bytes)
                pages = len(reader.pages)
                reader.close()
                digest = hashlib.sha256(Path(temp).read_bytes()).hexdigest()
                destination = directory/(digest+'.pdf')
                if destination.exists():
                    Path(temp).unlink()
                else:
                    os.replace(temp,destination)
                return str(destination),{'source_url':original_url,'final_url':url,'retrieved_at':now(),'sha256':digest,'pages':pages,'bytes':size,'content_type':content_type}
            finally:
                conn.close()
        raise ValueError('Too many PDF redirects')
    finally:
        if Path(temp).exists():
            Path(temp).unlink()

def import_pdf(source,directory,settings):
    reader = validate_pdf(source,settings.max_pdf_bytes)
    count = len(reader.pages)
    reader.close()
    digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    dest = Path(directory)/(digest+'.pdf')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():
        shutil.copyfile(source,dest)
    return str(dest),{'source_url':'user-provided local file','original_filename':Path(source).name,'retrieved_at':now(),'sha256':digest,'pages':count,'license':'User-authorized input'}

def inspect_pdf(path,metadata):
    reader = validate_pdf(path)
    try:
        text = reader.pages[0].extract_text() or ''
        first = norm(text)
        title = norm(metadata.get('title'))
        expected_doi = doi(metadata.get('doi'))
        found = [doi(x.rstrip(').,;]')) for x in re.findall(r'10\.\d{4,9}/[^\s<>"{}]+',text,re.I)]
        authors = surnames(metadata.get('author'))
        title_match = len(title) >= 12 and title in first
        author_match = bool(authors and all(a in first for a in authors[:3]))
        doi_match = bool(expected_doi and expected_doi in found)
        if doi_match and title_match or title_match and author_match and not (expected_doi and found and not doi_match):
            status = 'confirmed'
        elif expected_doi and found and not doi_match:
            status = 'mismatch'
        elif title_match or doi_match:
            status = 'probable'
        elif not first:
            status = 'needs_manual_review'
        else:
            status = 'mismatch'
        return status,{'doi_found':found,'doi_match':doi_match,'title_match':title_match,'author_match':author_match,'first_page_excerpt':text[:2500],'ocr_available':False,'limitation':'Scanned PDFs require external OCR; probable PDFs require explicit confirmation','page_count':len(reader.pages)}
    finally:
        reader.close()

def extract_first(source,destination):
    reader = validate_pdf(source)
    try:
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        destination = Path(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        temp = destination.with_suffix('.tmp')
        with temp.open('wb') as f:
            writer.write(f)
        os.replace(temp,destination)
    finally:
        reader.close()

def merge(task):
    plain, indexed = PdfWriter(), PdfWriter()
    readers = []
    count = 0
    for index,ref in enumerate(task.references,1):
        ref.first_page_path = ''
        if not ref.pdf_path or ref.pdf_match_status not in {'confirmed','probable'} or ref.pdf_match_status=='probable' and not ref.pdf_approved:
            continue
        try:
            current = hashlib.sha256(Path(ref.pdf_path).read_bytes()).hexdigest()
            if current != ref.pdf_evidence.get('sha256'):
                raise ValueError('PDF checksum changed; upload and verify again')
            destination = Path(task.output_path)/'First_Pages'/f'{index:03d}_{safe_name(ref.citation_key)}_first_page.pdf'
            extract_first(ref.pdf_path,destination)
            reader = PdfReader(destination)
            readers.append(reader)
            plain.add_page(reader.pages[0])
            indexed.add_page(reader.pages[0])
            indexed.add_outline_item(f'[{index}] {ref.citation_key}: '+ref.input_metadata.get('title',''),count)
            ref.first_page_path = str(destination)
            count += 1
        except Exception as exc:
            ref.errors.append('First-page extraction: '+str(exc))
    task.merged_pages = count
    for name,writer in [('Reference_First_Pages.pdf',plain),('Reference_First_Pages_Indexed.pdf',indexed)]:
        target = Path(task.output_path)/name
        if count:
            temp = target.with_suffix('.tmp')
            with temp.open('wb') as f:
                writer.write(f)
            os.replace(temp,target)
        elif target.exists():
            target.unlink()
    for reader in readers:
        reader.close()
    return count
