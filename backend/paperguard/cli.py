import argparse
import json
import sys
from pathlib import Path
from .config import Settings,ROOT,load_env
from .engine import Engine
from .storage import Store
from .reporting import export,summary
from .pdf import merge

def main(argv=None):
    load_env()
    parser = argparse.ArgumentParser(prog='paperguard',description='Evidence-based local reference audit')
    parser.add_argument('--data-dir',type=Path)
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init',help='Create local .env from example without overwriting')
    for name in ['audit','collect-pdf']:
        p = sub.add_parser(name)
        p.add_argument('project',nargs='?',default='.')
        p.add_argument('--bib',type=Path)
        p.add_argument('--main')
        p.add_argument('--semantic',action='store_true')
        p.add_argument('--offline',action='store_true')
        p.add_argument('--no-pdf',action='store_true')
    p = sub.add_parser('resume'); p.add_argument('task')
    p = sub.add_parser('retry'); p.add_argument('task'); p.add_argument('key')
    p = sub.add_parser('report'); p.add_argument('--task',required=True); p.add_argument('--format',choices=['html','xlsx','json','all'],default='all')
    p = sub.add_parser('upload-pdf'); p.add_argument('task'); p.add_argument('key'); p.add_argument('pdf',type=Path)
    p = sub.add_parser('approve-pdf'); p.add_argument('task'); p.add_argument('key')
    p = sub.add_parser('serve'); p.add_argument('--port',type=int,default=8765)
    sub.add_parser('clear-cache')
    args = parser.parse_args(argv)
    settings = Settings()
    if args.data_dir:
        settings.data_dir = args.data_dir.resolve()
    store = Store(settings.data_dir)
    engine = Engine(settings,store)
    try:
        if args.command == 'init':
            target = ROOT/'.env'
            if not target.exists():
                target.write_text((ROOT/'.env.example').read_text(encoding='utf-8'),encoding='utf-8')
            print('Config: '+str(target))
            return 0
        if args.command == 'serve':
            import uvicorn
            from .api import create_app
            print('PaperGuard: http://127.0.0.1:'+str(args.port))
            uvicorn.run(create_app(settings),host='127.0.0.1',port=args.port)
            return 0
        if args.command == 'clear-cache':
            store.clear_cache()
            print('Cache cleared')
            return 0
        if args.command in {'audit','collect-pdf'}:
            task = engine.create(args.bib or args.project,args.main,args.bib,args.semantic,args.offline,not args.no_pdf)
            task = engine.run(task.task_id)
        elif args.command in {'resume','retry'}:
            store.cancel(args.task,False)
            task = engine.run(args.task,args.key if args.command=='retry' else None)
        elif args.command == 'report':
            task = store.get(args.task)
            merge(task); export(task); store.save(task)
        else:
            task = store.get(args.task)
            ref = next(r for r in task.references if r.citation_key==args.key)
            task = engine.upload(args.task,ref.id,args.pdf) if args.command=='upload-pdf' else engine.approve(args.task,ref.id,'pdf')
        print(json.dumps(summary(task),ensure_ascii=False,indent=2))
        print('Output: '+task.output_path)
        # Partial results are useful and not a process failure; report status stays explicit.
        return 1 if task.status=='failed' else 0
    except (ValueError,KeyError,StopIteration,OSError) as exc:
        print('PaperGuard error: '+str(exc),file=sys.stderr)
        return 2
    finally:
        engine.sources.close()

if __name__ == '__main__':
    raise SystemExit(main())
