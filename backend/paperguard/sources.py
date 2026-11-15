import hashlib
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote
import httpx
from .models import SourceRecord, now
from .normalization import doi, norm, plain

_locks = {name:threading.Lock() for name in ['crossref','openalex','arxiv']}
_last = {}

def first(value):
    return value[0] if isinstance(value,list) and value else value if isinstance(value,str) else ''

def crossref_record(m):
    dates = {}
    for key in ('published','published-print','published-online','issued'):
        parts = m.get(key,{}).get('date-parts',[[]])[0]
        if parts:
            dates[key] = str(parts[0])
    return {'title':first(m.get('title')), 'author':' and '.join(', '.join(filter(None,[a.get('family'),a.get('given')])) for a in m.get('author',[])), 'year':next(iter(dates.values()),''), 'journal':first(m.get('container-title')), 'volume':m.get('volume',''), 'number':m.get('issue',''), 'pages':m.get('page',m.get('article-number','')), 'publisher':m.get('publisher',''), 'doi':doi(m.get('DOI')), 'url':m.get('URL',''), 'abstract':m.get('abstract',''), 'publication_years':dates, 'oa_locations':[]}

def openalex_record(m):
    source = (m.get('primary_location') or {}).get('source') or {}
    b = m.get('biblio') or {}
    abstract = m.get('abstract_inverted_index') or {}
    words = {pos:word for word,positions in abstract.items() for pos in positions}
    locations = []
    for location in m.get('locations',[]):
        if location and location.get('is_oa') and location.get('pdf_url'):
            locations.append({'url':location['pdf_url'],'license':location.get('license'),'provenance':'OpenAlex OA location','landing_page':location.get('landing_page_url')})
    return {'title':m.get('title') or '', 'author':' and '.join(a.get('author',{}).get('display_name','') for a in m.get('authorships',[])), 'year':str(m.get('publication_year') or ''),'journal':source.get('display_name',''),'volume':b.get('volume') or '','number':b.get('issue') or '','pages':'--'.join(str(x) for x in [b.get('first_page'),b.get('last_page')] if x),'publisher':source.get('host_organization_name') or '','doi':doi(m.get('doi')),'url':(m.get('primary_location') or {}).get('landing_page_url') or m.get('id',''),'abstract':' '.join(words[p] for p in sorted(words)), 'oa_locations':locations}

class Sources:
    def __init__(self, settings, store, client=None):
        self.settings, self.store = settings, store
        self.client = client or httpx.Client(timeout=httpx.Timeout(settings.timeout,connect=10),follow_redirects=False,headers={'User-Agent':'PaperGuard/1.0'+(' (mailto:'+settings.email+')' if settings.email else '')})

    def close(self):
        self.client.close()

    def _request(self, source, url, params):
        interval = 3.1 if source == 'arxiv' else 1.1
        with _locks[source]:
            time.sleep(max(0,interval-(time.monotonic()-_last.get(source,0))))
            for attempt in range(3):
                _last[source] = time.monotonic()
                try:
                    response = self.client.get(url,params=params)
                    if response.status_code in {429,500,502,503,504} and attempt < 2:
                        try:
                            delay = float(response.headers.get('retry-after',str(2**(attempt+1))))
                        except ValueError:
                            delay = 4
                        if delay > 30:
                            raise RuntimeError('rate_limited_retry_later')
                        time.sleep(max(interval,delay))
                        continue
                    if response.status_code == 404:
                        return None
                    response.raise_for_status()
                    return response
                except (httpx.TimeoutException,httpx.NetworkError):
                    if attempt == 2:
                        raise
                    time.sleep(2**(attempt+1))

    def query(self, source, kind, value):
        key = hashlib.sha256(json.dumps([source,kind,doi(value) if kind == 'doi' else norm(value)]).encode()).hexdigest()
        hit = self.store.cached(key,self.settings.cache_ttl)
        query = {'source':source,'query_type':kind,'query_value':value,'queried_at':now(),'cached':hit is not None,'status':'ok'}
        if hit is not None:
            query['retrieved_at'] = hit['retrieved_at']
            return [SourceRecord.model_validate(v) for v in hit['records']],query
        try:
            records = self._query(source,kind,value)
            query['retrieved_at'] = now()
            self.store.cache(key,{'records':[r.model_dump(mode='json') for r in records],'retrieved_at':query['retrieved_at']})
            return records,query
        except Exception as exc:
            # Do not persist exception URLs: some services put credentials in their query strings.
            query.update(status='error',error=type(exc).__name__,message='Source unavailable / request failed; check connectivity, credentials or rate limits')
            return [],query

    def _query(self, source, kind, value):
        raw = []
        if source == 'crossref':
            url = 'https://api.crossref.org/works'+('/'+quote(doi(value),safe='') if kind == 'doi' else '')
            params = {} if kind == 'doi' else {'query.bibliographic':plain(value),'rows':5}
            if self.settings.email:
                params['mailto'] = self.settings.email
            response = self._request(source,url,params)
            if response is not None:
                message = response.json()['message']
                raw = [(m,str(m.get('DOI','')),m.get('URL',''),crossref_record(m)) for m in ([message] if kind == 'doi' else message.get('items',[]))]
        elif source == 'openalex':
            url = 'https://api.openalex.org/works'+('/'+quote('https://doi.org/'+doi(value),safe=':/') if kind == 'doi' else '')
            params = {} if kind == 'doi' else {'search':plain(value),'per-page':5}
            if self.settings.openalex_key:
                params['api_key'] = self.settings.openalex_key
            response = self._request(source,url,params)
            if response is not None:
                message = response.json()
                raw = [(m,m.get('id',''),m.get('id',''),openalex_record(m)) for m in ([message] if kind == 'doi' else message.get('results',[]))]
        elif source == 'arxiv':
            response = self._request(source,'https://export.arxiv.org/api/query',{'search_query':('doi:'+doi(value) if kind == 'doi' else 'ti:"'+plain(value).replace('"','')+'"'),'max_results':5})
            if response is not None:
                ns = {'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}
                for e in ET.fromstring(response.text).findall('a:entry',ns):
                    get = lambda name:e.findtext(name,'',ns).strip()
                    record_id = get('a:id')
                    if '/errors' in record_id:
                        raise ValueError('arXiv query error')
                    locations = [{'url':l.get('href','').replace('http:','https:'),'provenance':'arXiv public repository','license':get('x:license')} for l in e.findall('a:link',ns) if l.get('title') == 'pdf']
                    metadata = {'title':get('a:title'),'author':' and '.join(a.findtext('a:name','',ns) for a in e.findall('a:author',ns)),'year':get('a:published')[:4],'doi':doi(get('x:doi')),'url':record_id,'abstract':get('a:summary'),'journal':get('x:journal_ref'),'oa_locations':locations}
                    raw.append(({'atom_entry':ET.tostring(e,encoding='unicode')},record_id,record_id,metadata))
        else:
            raise ValueError('Unknown source '+source)
        return [SourceRecord(source_name=source,source_record_id=rid,query_type=kind,query_value=value,source_url=url,raw_metadata=m,normalized_metadata=meta) for m,rid,url,meta in raw]

    def search(self, metadata):
        candidates, queries = [], []
        for source in self.settings.sources:
            identifier = doi(metadata.get('doi'))
            if identifier:
                found, query = self.query(source,'doi',identifier)
                candidates.extend(found)
                queries.append(query)
            else:
                found = []
            if metadata.get('title') and (not found or any(norm(r.normalized_metadata.get('title')) != norm(metadata['title']) for r in found)):
                found, query = self.query(source,'title',metadata['title'])
                candidates.extend(found)
                queries.append(query)
        return candidates,queries
