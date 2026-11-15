"""Check exactly the source files Git would publish; optionally build a source ZIP."""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SKIP_DIRS={'.git','.venv','node_modules','data','__pycache__','.pytest_cache','release','build','dist'}
PATTERNS=['.env','.env.*','*.pyc','*.egg-info/*','*.sqlite3*','*.log','docs/qa/*','docs/release-check-*.json','docs/online_smoke_result.json','docs/test-results.xml','.DS_Store','Thumbs.db']
SECRETS={
    'GitHub token':r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}',
    'AWS access key':r'(?:AKIA|ASIA)[A-Z0-9]{16}',
    'API secret':r'sk-[A-Za-z0-9_-]{24,}',
    'private key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'personal absolute path':r'(?i)[A-Z]:[\\/]+Users[\\/]+(?!Public\b)[^\\/\s`"\']+',
}

def excluded(name):
    if name=='.env.example':return False
    return bool(set(Path(name).parts)&SKIP_DIRS) or any(fnmatch.fnmatch(name,p) for p in PATTERNS)

def source_files():
    try:
        top=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','--show-toplevel'],stderr=subprocess.DEVNULL,text=True).strip()
        if Path(top).resolve()==ROOT:
            raw=subprocess.check_output(['git','-C',str(ROOT),'ls-files','--cached','--others','--exclude-standard','-z'])
            return sorted(set(n.decode('utf-8') for n in raw.split(b'\0') if n))
    except (OSError,subprocess.CalledProcessError):pass
    result=[]
    for base,dirs,files in os.walk(ROOT):
        dirs[:]=[d for d in dirs if d not in SKIP_DIRS and not d.endswith('.egg-info')]
        for name in files:
            relative=(Path(base)/name).relative_to(ROOT).as_posix()
            if not excluded(relative):result.append(relative)
    return sorted(result)

def check(files):
    failures=[]
    for name in files:
        path=ROOT/name
        if excluded(name):failures.append(name+': local/generated file is selected by Git');continue
        if path.is_symlink():failures.append(name+': symbolic link must be reviewed');continue
        if not path.is_file():failures.append(name+': selected file is missing');continue
        if path.stat().st_size>10*1024*1024:failures.append(name+': source file exceeds 10 MB');continue
        if path.suffix.lower() in {'.pdf','.sqlite3','.xlsx','.docx','.pptx'}:
            failures.append(name+': document/database is not part of the source-only release')
        try:text=path.read_text(encoding='utf-8')
        except (UnicodeDecodeError,OSError):continue
        for label,pattern in SECRETS.items():
            if re.search(pattern,text):failures.append(name+': possible '+label+'; inspect locally (value redacted)')
    for required in ['LICENSE','NOTICE','README.md','.env.example','frontend/package-lock.json','backend/pyproject.toml','.github/workflows/ci.yml']:
        if required not in files:failures.append(required+': required source file missing')
    return failures

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    files=source_files()
    failures=check(files)
    result={'source_files':len(files),'total_bytes':sum((ROOT/name).stat().st_size for name in files if (ROOT/name).is_file()),'passed':not failures,'failures':failures}
    if args.archive and not failures:
        target=args.archive.resolve()
        if target.is_relative_to(ROOT) and target.relative_to(ROOT).parts[0]!='release':
            raise ValueError('Write in release/ or outside this checkout')
        target.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name in files:archive.write(ROOT/name,'PaperGuard/'+name)
        result.update(archive_name=target.name,archive_bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if not failures else 1

if __name__=='__main__':raise SystemExit(main())
