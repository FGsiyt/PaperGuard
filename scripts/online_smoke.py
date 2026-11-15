import json
from pathlib import Path
from paperguard.config import Settings,ROOT,load_env
from paperguard.storage import Store
from paperguard.engine import Engine
from paperguard.sources import Sources

load_env()
settings=Settings()
settings.sources=('crossref','openalex','arxiv')
store=Store(settings.data_dir)
engine=Engine(settings,store)
task=engine.create(ROOT/'examples'/'resnet')
task=engine.run(task.task_id)
result={'task_id':task.task_id,'output_path':task.output_path,'status':task.status,'merged_pages':task.merged_pages,'references':[{'key':r.citation_key,'status':r.verification_status.value,'queries':r.queries,'pdf_status':r.pdf_status,'pdf_match':r.pdf_match_status,'sources':[c.source_name for c in r.candidate_matches],'errors':r.errors} for r in task.references]}
(ROOT/'docs'/'online_smoke_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
engine.sources.close()
