import json
import os
import secrets
import shutil
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import ROOT, Settings, load_env
from .storage import Store
from .engine import Engine
from .reporting import export, summary
from .pdf import merge

class CreateAudit(BaseModel):
    project_path: str = Field(min_length=1)
    main: str | None = None
    semantic: bool = False
    offline: bool = False
    collect: bool = True

class Preferences(BaseModel):
    sources: list[str]
    timeout: float = Field(ge=3,le=90)
    cache_ttl: int = Field(ge=60,le=31536000)
    email: str = ''
    llm_base: str = ''
    llm_model: str = ''

def extract_zip(source,destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries)>3000 or sum(e.file_size for e in entries)>100*1024*1024:
            raise ValueError('ZIP exceeds 3000 files or 100 MB uncompressed')
        for e in entries:
            normalized = e.filename.replace('\\','/')
            path = (destination/normalized).resolve()
            if not path.is_relative_to(destination) or ':' in normalized or (e.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe ZIP entry')
            if e.file_size>20*1024*1024 or e.file_size/max(e.compress_size,1)>500:
                raise ValueError('ZIP entry too large or compression ratio unsafe')
        for e in entries:
            path = destination/e.filename.replace('\\','/')
            if e.is_dir():
                path.mkdir(parents=True,exist_ok=True)
            else:
                path.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(e) as src,path.open('wb') as dst:
                    shutil.copyfileobj(src,dst)

def create_app(settings=None):
    load_env()
    settings = settings or Settings()
    store = Store(settings.data_dir)
    preferences = settings.data_dir/'preferences.json'
    if preferences.exists():
        try:
            config = Preferences.model_validate_json(preferences.read_text(encoding='utf-8'))
            for key,value in config.model_dump().items():
                setattr(settings,key,tuple(value) if key=='sources' else value)
        except Exception:
            pass
    engine = Engine(settings,store)
    executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix='paperguard')
    active,guard = set(),Lock()
    token = secrets.token_urlsafe(32)
    app = FastAPI(title='PaperGuard',version='1.0.0')
    app.state.store,app.state.engine,app.state.token = store,engine,token
    for task in store.list():
        if task.status in {'running','queued'}:
            task.status,task.current_stage = 'interrupted','Server restarted; resume task'
            store.save(task)

    @app.middleware('http')
    async def local_only(request,call_next):
        host = urlsplit('//'+request.headers.get('host','')).hostname
        if host not in {'127.0.0.1','localhost','::1','testserver'}:
            return JSONResponse({'detail':'Local host required'},status_code=403)
        if request.method not in {'GET','HEAD','OPTIONS'}:
            origin = request.headers.get('origin')
            if origin and urlsplit(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail':'Cross-origin mutation blocked'},status_code=403)
            if not secrets.compare_digest(request.headers.get('x-paperguard-token',''),token):
                return JSONResponse({'detail':'Local session token required'},status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def get_task(task_id):
        try:
            return store.get(task_id)
        except KeyError:
            raise HTTPException(404,'Task not found')

    def enqueue(task,retry=None):
        with guard:
            if task.task_id in active:
                raise HTTPException(409,'Task is already queued or running')
            active.add(task.task_id)
            store.cancel(task.task_id,False)
            task.status,task.current_stage = 'queued','queued'
            store.save(task)
        def work():
            try:
                engine.run(task.task_id,retry)
            finally:
                with guard:
                    active.discard(task.task_id)
        executor.submit(work)
        return task.model_dump(mode='json')

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        return JSONResponse({'detail':str(exc)},status_code=400)

    @app.get('/api/tasks')
    def tasks():
        return [summary(t)|{'progress':t.progress,'current_stage':t.current_stage,'created_at':t.created_at} for t in store.list()]

    def require_reference(task_id,reference_id):
        task = get_task(task_id)
        ref = next((r for r in task.references if r.id == reference_id),None)
        if ref is None:
            raise HTTPException(404,'Reference not found')
        return task,ref

    @app.post('/api/tasks')
    def create(body:CreateAudit):
        return enqueue(engine.create(body.project_path,body.main,semantic=body.semantic,offline=body.offline,collect=body.collect))

    async def save_upload(file,destination,max_bytes):
        size = 0
        with Path(destination).open('wb') as f:
            while chunk := await file.read(65536):
                size += len(chunk)
                if size>max_bytes:
                    raise HTTPException(413,'Upload exceeds size limit')
                f.write(chunk)

    @app.post('/api/import')
    async def import_project(file:UploadFile=File(...),semantic:bool=Form(False),offline:bool=Form(False),collect:bool=Form(True)):
        suffix = Path(file.filename or '').suffix.lower()
        if suffix not in {'.bib','.zip'}:
            raise HTTPException(400,'Upload .bib or a ZIP of a LaTeX project. Manuscript PDF reference extraction is not supported.')
        folder = settings.data_dir/'imports'/secrets.token_hex(10)
        folder.mkdir(parents=True)
        source = folder/('input'+suffix)
        try:
            await save_upload(file,source,50*1024*1024)
            if suffix == '.zip':
                extracted = folder/'project'
                extract_zip(source,extracted)
                children = list(extracted.iterdir())
                project = children[0] if len(children)==1 and children[0].is_dir() else extracted
            else:
                project = source
            task = engine.create(project,semantic=semantic,offline=offline,collect=collect)
            return enqueue(task)
        except Exception:
            if folder.exists():
                shutil.rmtree(folder)
            raise

    @app.get('/api/tasks/{task_id}')
    def detail(task_id:str):
        return get_task(task_id).model_dump(mode='json')

    @app.post('/api/tasks/{task_id}/cancel')
    def cancel(task_id:str):
        get_task(task_id)
        store.cancel(task_id)
        return {'status':'cancel_requested','message':'Cancellation takes effect after the current reference / network timeout'}

    @app.post('/api/tasks/{task_id}/resume')
    def resume(task_id:str):
        return enqueue(get_task(task_id))

    @app.post('/api/tasks/{task_id}/retry/{reference_id}')
    def retry(task_id:str,reference_id:str):
        task,ref = require_reference(task_id,reference_id)
        # Retry queries use cache except failed queries (which are never cached).
        ref.errors = []
        return enqueue(task,ref.citation_key)

    @app.post('/api/tasks/{task_id}/pdf/{reference_id}')
    async def upload_pdf(task_id:str,reference_id:str,file:UploadFile=File(...)):
        require_reference(task_id,reference_id)
        fd,path = tempfile.mkstemp(suffix='.pdf',dir=settings.data_dir)
        os.close(fd)
        try:
            await save_upload(file,path,settings.max_pdf_bytes)
            return engine.upload(task_id,reference_id,path).model_dump(mode='json')
        finally:
            Path(path).unlink(missing_ok=True)

    @app.post('/api/tasks/{task_id}/approve/{reference_id}/{kind}')
    def approve(task_id:str,reference_id:str,kind:str):
        require_reference(task_id,reference_id)
        return engine.approve(task_id,reference_id,kind).model_dump(mode='json')

    @app.get('/api/tasks/{task_id}/files')
    def files(task_id:str):
        task = get_task(task_id)
        root = Path(task.output_path)
        return [{'name':str(p.relative_to(root)).replace('\\','/'),'bytes':p.stat().st_size} for p in sorted(root.rglob('*')) if p.is_file()]

    @app.get('/api/tasks/{task_id}/files/{filename:path}')
    def artifact(task_id:str,filename:str):
        task = get_task(task_id)
        root = Path(task.output_path).resolve()
        target = (root/filename).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(404,'Artifact not found')
        # Standalone reports contain JavaScript; download them instead of granting app origin.
        return FileResponse(target,filename=target.name,content_disposition_type='inline' if target.suffix=='.pdf' else 'attachment')

    @app.delete('/api/tasks/{task_id}')
    def delete_task(task_id:str):
        task = get_task(task_id)
        if task.status in {'queued','running'}:
            raise HTTPException(409,'Stop the task before deleting')
        root = (settings.data_dir/'tasks').resolve()
        target = Path(task.output_path).resolve()
        if target.parent != root or target.name != task_id:
            raise ValueError('Unsafe task path')
        if target.exists():
            shutil.rmtree(target)
        # Uploaded project copies are owned by this task; original local paths remain intact.
        imported = Path(task.project_path).resolve()
        imports_root = (settings.data_dir/'imports').resolve()
        if imported.is_relative_to(imports_root):
            relative = imported.relative_to(imports_root)
            if relative.parts:
                owned = imports_root/relative.parts[0]
                if owned.parent == imports_root and owned.is_dir():
                    shutil.rmtree(owned)
        store.delete(task_id)
        return {'deleted':task_id}

    @app.get('/api/settings')
    def settings_view():
        return {'sources':settings.sources,'timeout':settings.timeout,'cache_ttl':settings.cache_ttl,'email':settings.email,'llm_base':settings.llm_base,'llm_model':settings.llm_model,'llm_key_configured':bool(settings.llm_key),'openalex_key_configured':bool(settings.openalex_key),'data_dir':str(settings.data_dir),'concurrency':1,'env_file':str(ROOT/'.env')}

    @app.post('/api/settings')
    def settings_update(body:Preferences):
        if any(source not in {'crossref','openalex','arxiv'} for source in body.sources) or not body.sources:
            raise ValueError('Choose Crossref, OpenAlex and/or arXiv')
        if active:
            raise HTTPException(409,'Wait for active tasks to finish before changing settings')
        if body.llm_base and urlsplit(body.llm_base).scheme not in {'http','https'}:
            raise ValueError('LLM base must be an HTTP(S) endpoint')
        for key,value in body.model_dump().items():
            setattr(settings,key,tuple(value) if key=='sources' else value)
        preferences.write_text(body.model_dump_json(indent=2),encoding='utf-8')
        return settings_view()

    @app.delete('/api/cache')
    def clear_cache():
        if active:
            raise HTTPException(409,'Wait for active tasks to finish')
        store.clear_cache()
        return {'cleared':True}

    dist = ROOT/'frontend'/'dist'
    if dist.exists():
        if (dist/'assets').exists():
            app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
        @app.get('/',response_class=HTMLResponse)
        def index():
            text = (dist/'index.html').read_text(encoding='utf-8')
            return HTMLResponse(text.replace('__PAPERGUARD_TOKEN__',token),headers={'Cache-Control':'no-store'})
    else:
        @app.get('/',response_class=HTMLResponse)
        def missing_frontend():
            return '<h1>PaperGuard</h1><p>Build frontend: cd frontend &amp;&amp; npm ci &amp;&amp; npm run build</p><a href="/docs">API docs</a>'
    return app
