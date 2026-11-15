import hashlib
import json
from pathlib import Path
from .models import AuditTask, now
from .parsers import parse_project
from .sources import Sources
from .verification import classify
from .pdf import download_pdf,import_pdf,inspect_pdf,merge
from .semantic import audit_semantic
from .reporting import export

class Engine:
    def __init__(self,settings,store,sources=None):
        self.settings,self.store = settings,store
        self.sources = sources or Sources(settings,store)

    def create(self,project,main=None,bib=None,semantic=False,offline=False,collect=True):
        refs,findings,order,basis,fingerprint,main_tex,bibs = parse_project(project,main,bib)
        if not refs and not findings:
            raise ValueError('No bibliography entries found')
        task = AuditTask(project_path=str(Path(project).resolve()),main_tex=main_tex,bib_files=bibs,references=refs,findings=findings,reference_order=order,order_basis=basis,input_hash=fingerprint,options={'semantic':semantic,'offline':offline,'collect':collect})
        task.output_path = str(self.settings.data_dir/'tasks'/task.task_id)
        Path(task.output_path).mkdir(parents=True,exist_ok=True)
        for sub in ['Original_PDFs','First_Pages','Logs']:
            (Path(task.output_path)/sub).mkdir(exist_ok=True)
        self.store.save(task)
        return task

    def run(self,task_id,retry_key=None):
        task = self.store.get(task_id)
        try:
            _,_,_,_,fingerprint,_,_ = parse_project(task.project_path,task.main_tex,task.bib_files[0] if not task.main_tex and len(task.bib_files)==1 else None)
            if fingerprint != task.input_hash:
                raise ValueError('Input files changed since task creation; create a new audit')
            task.status = 'running'
            task.error_summary = []
            self.store.save(task)
            for index,ref in enumerate(task.references):
                if self.store.cancelled(task_id):
                    task.status = 'cancelled'
                    break
                if retry_key and ref.citation_key != retry_key or ref.processed and not retry_key:
                    continue
                task.current_stage = 'Verifying '+ref.citation_key
                task.progress = round(index/max(len(task.references),1)*90,1)
                self.store.save(task)
                try:
                    if not task.options.get('offline'):
                        candidates,queries = self.sources.search(ref.input_metadata)
                        ref.candidate_matches,ref.queries = candidates,queries
                        ref.verification_status,ref.selected_match,ref.metadata_fields = classify(ref.input_metadata,candidates,queries)
                    else:
                        ref.queries = [{'source':'none','status':'disabled','queried_at':now(),'message':'Offline mode: no authenticity claim'}]
                    if task.options.get('collect') and not task.options.get('offline') and not ref.pdf_path:
                        self.collect(ref,task)
                    audit_semantic(ref,self.settings,task.options.get('semantic',False))
                except Exception as exc:
                    ref.errors.append(type(exc).__name__+': '+str(exc)[:300])
                ref.processed = True
                ref.updated_at = now()
                self.store.save(task)
            if task.status == 'running':
                task.status = 'partial' if any(not r.processed or r.errors or r.verification_status.value!='verified' or task.options.get('collect') and not (r.pdf_path and (r.pdf_match_status=='confirmed' or r.pdf_match_status=='probable' and r.pdf_approved)) for r in task.references) or any(f.severity=='error' for f in task.findings) else 'completed'
                task.progress = 100
            task.current_stage = 'Exporting reports'
            merge(task)
            export(task)
            task.current_stage = task.status
            self.store.save(task)
        except Exception as exc:
            task.status = 'failed'
            task.error_summary.append(type(exc).__name__+': '+str(exc)[:400])
            self.store.save(task)
            export(task)
        return task

    def collect(self,ref,task):
        locations = []
        # Use only metadata belonging to the target identity, including agreeing sources.
        for c in ref.candidate_matches:
            basis = c.match_basis
            if basis.get('title_similarity',0)>=.95 and (basis.get('author_sequence_match') or basis.get('doi_exact')):
                locations.extend(c.normalized_metadata.get('oa_locations',[]))
        if not locations:
            ref.pdf_status = 'not_available'
            return
        for location in locations:
            try:
                path,evidence = download_pdf(location['url'],Path(task.output_path)/'Original_PDFs',self.settings)
                status,match = inspect_pdf(path,ref.input_metadata)
                ref.pdf_path,ref.pdf_match_status = path,status
                ref.pdf_evidence = {**evidence,**match,'oa_location':location}
                ref.pdf_status = 'downloaded' if status == 'confirmed' else 'needs_manual_review'
                if status in {'confirmed','probable'}:
                    return
            except Exception as exc:
                ref.errors.append('PDF acquisition: '+type(exc).__name__+': '+str(exc)[:250])
        if not ref.pdf_path:
            ref.pdf_status = 'download_failed'

    def upload(self,task_id,reference_id,source):
        task = self.store.get(task_id)
        if task.status in {'running','queued'}:
            raise ValueError('Wait for the task to stop before uploading a PDF')
        ref = next(r for r in task.references if r.id == reference_id)
        path,evidence = import_pdf(source,Path(task.output_path)/'Original_PDFs',self.settings)
        status,match = inspect_pdf(path,ref.input_metadata)
        ref.pdf_path,ref.pdf_status,ref.pdf_match_status,ref.pdf_approved = path,'user_uploaded',status,False
        ref.pdf_evidence = {**evidence,**match}
        audit_semantic(ref,self.settings,task.options.get('semantic',False))
        merge(task)
        export(task)
        self.store.save(task)
        return task

    def approve(self,task_id,reference_id,kind):
        task = self.store.get(task_id)
        if task.status in {'running','queued'}:
            raise ValueError('Wait for the task to stop before reviewing changes')
        ref = next(r for r in task.references if r.id == reference_id)
        if kind == 'pdf':
            if ref.pdf_match_status != 'probable':
                raise ValueError('Only probable PDFs can be manually approved; mismatch is excluded')
            ref.pdf_approved = True
            ref.pdf_evidence['approved_at'] = now()
            merge(task)
        elif kind == 'correction':
            ref.correction_approved = True
        else:
            raise ValueError('Unknown approval kind')
        export(task)
        self.store.save(task)
        return task
