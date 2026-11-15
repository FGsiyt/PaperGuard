import hashlib
import re
from pathlib import Path
from collections import Counter
import bibtexparser
from bibtexparser.bparser import BibTexParser
from .models import Reference, CitationOccurrence, Finding
from .normalization import norm, doi

CITES = {'cite','citep','citet','citealp','citealt','citeauthor','citeyear','citeyearpar','parencite','autocite','textcite','footcite','supercite','nocite','Cite','Citep','Citet','Parencite','Textcite'}

def strip_comments(text):
    chars = list(text)
    i = 0
    while i < len(chars):
        if chars[i] == '%':
            k = i-1
            while k >= 0 and chars[k] == '\\':
                k -= 1
            if (i-1-k) % 2 == 0:
                while i < len(chars) and chars[i] != '\n':
                    chars[i] = ' '
                    i += 1
                continue
        i += 1
    return ''.join(chars)

def group(text, start, opening='{', closing='}'):
    if start >= len(text) or text[start] != opening:
        raise ValueError('Expected '+opening)
    depth, i = 1, start+1
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                return text[start+1:i], i+1
        i += 1
    raise ValueError('Unbalanced group')

def commands(text):
    i = 0
    while i < len(text):
        if text[i] != '\\':
            i += 1
            continue
        start = i
        i += 1
        match = re.match(r'[A-Za-z]+',text[i:])
        if not match:
            i += 1
            continue
        name = match[0]
        i += len(name)
        if i < len(text) and text[i] == '*':
            i += 1
        # Ignore literal/code environments, including their apparent citations.
        if name in {'verb','lstinline'} and i < len(text) and not text[i].isspace():
            stop = text.find(text[i],i+1)
            i = len(text) if stop < 0 else stop+1
            continue
        j = i
        while j < len(text) and text[j].isspace():
            j += 1
        try:
            while j < len(text) and text[j] == '[':
                _, j = group(text,j,'[',']')
                while j < len(text) and text[j].isspace():
                    j += 1
            if j < len(text) and text[j] == '{':
                arg, end = group(text,j)
                if name == 'begin' and arg in {'verbatim','lstlisting','minted','comment'}:
                    marker = '\\end{'+arg+'}'
                    stop = text.find(marker,end)
                    i = len(text) if stop < 0 else stop+len(marker)
                    continue
                yield name, arg, start, end
                # Newcommand definitions must not create real citation occurrences.
                if name in {'newcommand','renewcommand','providecommand','DeclareRobustCommand'}:
                    k = end
                    while k < len(text) and (text[k].isspace() or text[k] == '['):
                        if text[k] == '[':
                            _, k = group(text,k,'[',']')
                        else:
                            k += 1
                    if k < len(text) and text[k] == '{':
                        _, k = group(text,k)
                    i = k
                else:
                    # Scan unknown macro bodies for nested known commands.
                    i = end if name in CITES | {'input','include','bibliography','addbibresource','section','subsection','chapter','bibcite','bibitem'} else j+1
        except ValueError:
            yield '__malformed__', name, start, len(text)

def raw_entries(text):
    pattern = re.compile(r'@([A-Za-z]+)\s*([({])')
    pos = 0
    while (m := pattern.search(text,pos)):
        opening = m[2]
        try:
            _, end = group(text,m.end()-1,opening,'}' if opening == '{' else ')')
        except ValueError:
            yield m[1], text[m.start():], m.start(), 'Unbalanced BibTeX entry'
            return
        yield m[1], text[m.start():end], m.start(), ''
        pos = end

def parse_bib(path):
    text = path.read_text(encoding='utf-8-sig')
    records, findings, macros = [], [], ''
    # Collect all @string definitions first, including definitions after entries.
    pieces = list(raw_entries(text))
    macros = '\n'.join(raw for typ,raw,_,err in pieces if typ.lower() == 'string' and not err)
    for typ, raw, start, error in pieces:
        if typ.lower() in {'string','comment','preamble'}:
            continue
        line = text.count('\n',0,start)+1
        try:
            if error:
                raise ValueError(error)
            parser = BibTexParser(common_strings=True)
            parser.ignore_nonstandard_types = False
            parser.homogenize_fields = False
            parser.interpolate_strings = True
            db = bibtexparser.loads(macros+'\n'+raw,parser=parser)
            if len(db.entries) != 1:
                raise ValueError('Entry could not be parsed')
            entry = dict(db.entries[0])
            key = entry.pop('ID')
            kind = entry.pop('ENTRYTYPE')
            records.append(Reference(citation_key=key,entry_type=kind,raw_bibtex=raw,input_metadata={k:str(v) for k,v in entry.items()},source_file=str(path),source_line=line))
        except Exception as exc:
            findings.append(Finding(rule_id='bib_parse_error',category='parser',severity='error',message=str(exc),source_location={'file':str(path),'line':line},evidence={'raw':raw}))
    if not pieces and text.strip():
        findings.append(Finding(rule_id='bib_parse_error',category='parser',severity='error',message='No valid BibTeX entries',source_location={'file':str(path)}))
    return records,findings

def parse_project(project, main=None, bib=None):
    project = Path(project).resolve()
    root = project if project.is_dir() else project.parent
    findings, citations, bibs, visited, ordered, file_hashes = [], [], [], set(), [], []
    def finding(rule,message,path=None,line=None,**evidence):
        findings.append(Finding(rule_id=rule,message=message,source_location={'file':str(path or root),'line':line},evidence=evidence))
    def within(path):
        path = path.resolve()
        if not path.is_relative_to(root):
            raise ValueError('Project include outside root: '+str(path))
        return path
    section = ['']
    def walk(path, stack=()):
        path = within(path)
        if path in stack:
            finding('include_cycle','Recursive include skipped',path)
            return
        if not path.exists():
            finding('missing_file','Included file does not exist',path)
            return
        if len(stack) > 60:
            finding('include_depth','Include depth exceeds 60',path)
            return
        text = path.read_text(encoding='utf-8-sig')
        visited.add(path)
        file_hashes.append((str(path),hashlib.sha256(text.encode()).hexdigest()))
        clean = strip_comments(text)
        for cmd,arg,start,end in commands(clean):
            line = clean.count('\n',0,start)+1
            if cmd in {'input','include'}:
                target = root / arg.strip()
                if not target.suffix:
                    target = target.with_suffix('.tex')
                if not target.exists():
                    target = path.parent / arg.strip()
                    if not target.suffix:
                        target = target.with_suffix('.tex')
                try:
                    walk(target,stack+(path,))
                except ValueError as exc:
                    finding('unsafe_include',str(exc),path,line)
            elif cmd in {'bibliography','addbibresource'}:
                for item in arg.split(','):
                    target = root / item.strip()
                    if not target.suffix:
                        target = target.with_suffix('.bib')
                    try:
                        target = within(target)
                        if target not in bibs:
                            bibs.append(target)
                    except ValueError as exc:
                        finding('unsafe_include',str(exc),path,line)
            elif cmd in {'section','subsection','chapter'}:
                section[0] = arg
            elif cmd in CITES:
                keys = [k.strip() for k in arg.split(',')]
                if not arg.strip() or any(not k or re.search(r'[\s{}\\]',k) for k in keys):
                    finding('malformed_citation','Empty or malformed citation',path,line,raw=text[start:end])
                for key in filter(None,keys):
                    citations.append(CitationOccurrence(citation_key=key,source_file=str(path),line_number=line,command=cmd,context_before=clean[max(0,start-350):start],cited_text=text[start:end],context_after=clean[end:end+250],section=section[0]))
                    if key not in ordered and key != '*':
                        ordered.append(key)
            elif cmd == '__malformed__':
                finding('malformed_latex','Unbalanced argument for '+arg,path,line)
            elif cmd in {'newcommand','renewcommand','providecommand','def','DeclareRobustCommand'}:
                finding('macro_limitation','Custom macro is not expanded; inspect citations inside macro calls',path,line,macro=arg)
    selected = None
    if bib or project.suffix.lower() == '.bib':
        bibs = [Path(bib or project).resolve()]
    else:
        if project.is_file() and project.suffix == '.tex':
            selected = project
        elif main:
            selected = within(root/main)
        else:
            mains = [p for p in root.glob('*.tex') if '\\documentclass' in strip_comments(p.read_text(encoding='utf-8-sig'))]
            if len(mains) != 1:
                raise ValueError('Cannot uniquely identify main .tex; specify --main')
            selected = mains[0]
        walk(selected)
        if not bibs:
            bibs = sorted(root.glob('*.bib'))
            finding('bib_fallback','No bibliography directive; reading root .bib files')
    refs = []
    for path in bibs:
        if not path.is_file():
            finding('missing_bib','Bibliography file does not exist',path)
            continue
        result, errors = parse_bib(path)
        refs.extend(result)
        findings.extend(errors)
        file_hashes.append((str(path),hashlib.sha256(path.read_bytes()).hexdigest()))
    counts = Counter(r.citation_key for r in refs)
    allkeys = set(counts)
    cited = {c.citation_key for c in citations}
    for key,count in counts.items():
        if count > 1:
            finding('duplicate_key','Duplicate citation key: '+key,key=key,count=count)
    for c in citations:
        if c.citation_key not in allkeys and c.citation_key != '*':
            finding('missing_key','Citation has no BibTeX entry: '+c.citation_key,c.source_file,c.line_number,key=c.citation_key)
    seen = {}
    for ref in refs:
        ref.citation_locations = [c for c in citations if c.citation_key == ref.citation_key and c.command != 'nocite']
        if selected and '*' not in cited and ref.citation_key not in cited:
            finding('uncited_entry','Uncited BibTeX entry: '+ref.citation_key,ref.source_file,ref.source_line)
        identity = doi(ref.input_metadata.get('doi')) or norm(ref.input_metadata.get('title'))
        if identity and identity in seen:
            finding('duplicate_reference','Possible duplicate reference',keys=[seen[identity],ref.citation_key])
        seen[identity] = ref.citation_key
    basis = 'BibTeX entry order' if not selected else 'Source citation encounter order; final compiled bibliography numbering is unconfirmed'
    if selected:
        aux = selected.with_suffix('.aux')
        bbl = selected.with_suffix('.bbl')
        compiled = []
        if aux.exists():
            ac = list(commands(strip_comments(aux.read_text(encoding='utf-8-sig'))))
            labels = []
            for cmd,arg,_,end in ac:
                if cmd == 'bibcite':
                    text = strip_comments(aux.read_text(encoding='utf-8-sig'))
                    rest = text[end:].lstrip()
                    try:
                        label,_ = group(rest,0)
                        labels.append((int(label),arg))
                    except (ValueError,IndexError):
                        pass
            compiled = [key for _,key in sorted(labels)]
            if compiled:
                basis = 'Numeric bibcite labels from '+str(aux)+'; rebuild LaTeX if stale'
        if not compiled and bbl.exists():
            compiled = [arg for cmd,arg,_,_ in commands(strip_comments(bbl.read_text(encoding='utf-8-sig'))) if cmd == 'bibitem']
            if compiled:
                basis = 'bibitem sequence from '+str(bbl)+'; rebuild LaTeX if stale'
        if compiled:
            ordered = compiled
        else:
            finding('order_unconfirmed','No readable compiled bibliography order; using source citation order, then uncited entries')
    ordered += [r.citation_key for r in refs if r.citation_key not in ordered]
    positions = {k:i for i,k in enumerate(ordered)}
    refs.sort(key=lambda r:positions.get(r.citation_key,999999))
    fingerprint = hashlib.sha256(repr(sorted(file_hashes)).encode()).hexdigest()
    return refs,findings,ordered,basis,fingerprint,str(selected) if selected else None,[str(p) for p in bibs]
