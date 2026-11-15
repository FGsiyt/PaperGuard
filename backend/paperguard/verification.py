from .models import FieldComparison, Verification
from .normalization import norm, doi, similarity, authors_match, venue_equivalent

FIELDS = ['title','author','year','journal','volume','number','pages','publisher','doi','url']

def comparisons(metadata, record):
    result = []
    for name in FIELDS:
        a = metadata.get(name,'') or (metadata.get('booktitle','') if name == 'journal' else '')
        b = str(record.normalized_metadata.get(name,'') or '')
        note = ''
        if not a and not b:
            status = 'not_comparable'
        elif not a:
            status = 'missing_in_input'
        elif not b:
            status = 'missing_in_source'
        elif (doi(a)==doi(b) if name=='doi' else a == b):
            status = 'match'
        elif norm(a)==norm(b) or name == 'author' and authors_match(a,b) or name == 'journal' and venue_equivalent(a,b):
            status = 'minor_difference'
            note = 'Formatting, initials or venue abbreviation; compare original strings'
        elif name == 'year' and a in record.normalized_metadata.get('publication_years',{}).values():
            status = 'minor_difference'
            note = 'Year matches a publication stage: '+str(record.normalized_metadata['publication_years'])
        elif name == 'year':
            status = 'mismatch'
            note = 'May reflect early access versus issue year; review publication stages'
        else:
            status = 'mismatch'
        result.append(FieldComparison(field_name=name,input_value=a,verified_value=b,comparison_status=status,difference_explanation=note,source_name=record.source_name))
    return result

def classify(metadata, candidates, queries):
    for c in candidates:
        m = c.normalized_metadata
        exact = bool(doi(metadata.get('doi')) and doi(metadata.get('doi')) == doi(m.get('doi')))
        title = similarity(metadata.get('title'),m.get('title'))
        authors = authors_match(metadata.get('author'),m.get('author'))
        year = bool(metadata.get('year') and metadata.get('year') == str(m.get('year')))
        venue = venue_equivalent(metadata.get('journal',metadata.get('booktitle','')),m.get('journal','')) if m.get('journal') else False
        c.match_basis = {'doi_exact':exact,'title_similarity':round(title,4),'author_sequence_match':authors,'year_match':year,'venue_match':venue}
        c.score = round(.48*exact+.32*title+.12*authors+.05*year+.03*venue,4)
        if not exact:
            c.score = round(.70*title+.18*authors+.08*year+.04*venue,4)
    candidates.sort(key=lambda c:c.score,reverse=True)
    strong = [c for c in candidates if c.match_basis['doi_exact'] or c.match_basis['title_similarity'] >= .95 and c.match_basis['author_sequence_match'] and c.match_basis['year_match']]
    if strong:
        # A DOI may be real yet point at a wholly different paper. Keep the conflict visible.
        exacts = [c for c in strong if c.match_basis['doi_exact']]
        selected = exacts[0] if exacts else strong[0]
        # A source lacking a DOI can still agree with an identified record.
        # Conversely, equal IDs do not resolve conflicting source metadata.
        baseline = selected.normalized_metadata
        conflicting = False
        for candidate in strong:
            other = candidate.normalized_metadata
            left,right = doi(baseline.get('doi')),doi(other.get('doi'))
            if left and right and left != right:
                conflicting = True
            if baseline.get('title') and other.get('title') and similarity(baseline['title'],other['title']) < .88:
                conflicting = True
            if baseline.get('author') and other.get('author') and not authors_match(baseline['author'],other['author']):
                conflicting = True
        fields = comparisons(metadata,selected)
        if conflicting:
            return Verification.manual_review, selected, fields
        if metadata.get('title') and selected.match_basis['title_similarity'] < .88:
            return Verification.metadata_mismatch,selected,fields
        critical = {'title','author','year','doi','journal','volume','number','pages','publisher'}
        mismatch = any(f.field_name in critical and f.comparison_status == 'mismatch' for f in fields)
        return Verification.metadata_mismatch if mismatch else Verification.verified,selected,fields
    plausible = [c for c in candidates if c.match_basis['title_similarity'] >= .72]
    if plausible:
        return Verification.possible_match,plausible[0],comparisons(metadata,plausible[0])
    status = Verification.unverified if not queries or any(q['status']=='error' for q in queries) else Verification.not_found
    return status,None,[]

def suggested_fields(ref):
    if not ref.selected_match or ref.verification_status not in {Verification.verified,Verification.metadata_mismatch}:
        return {}
    basis = ref.selected_match.match_basis
    # Never rewrite the input to match an unrelated paper found through a wrong DOI.
    if basis.get('title_similarity',0) < .95 or not basis.get('author_sequence_match'):
        return {}
    safe = {}
    for f in ref.metadata_fields:
        if f.comparison_status in {'missing_in_input','mismatch'} and f.verified_value and f.field_name not in {'url','year','author'}:
            safe['booktitle' if f.field_name=='journal' and ref.entry_type in {'inproceedings','conference','incollection'} else f.field_name] = f.verified_value
    return safe

def bibtex(task, approved_only=False):
    blocks, changes = [], []
    from .parsers import raw_entries
    from pathlib import Path
    macros = []
    for name in task.bib_files:
        path = Path(name)
        if path.exists():
            for typ,raw,_,err in raw_entries(path.read_text(encoding='utf-8-sig')):
                if typ.lower()=='string' and not err and raw not in macros:
                    macros.append(raw)
    blocks.extend(macros)
    for r in task.references:
        updates = suggested_fields(r) if not approved_only or r.correction_approved else {}
        if not updates and r.raw_bibtex:
            blocks.append(r.raw_bibtex)
            continue
        if not updates:
            # Fully preserve the original text, macros having been resolved in the export below.
            fields = dict(r.input_metadata)
        else:
            fields = {**r.input_metadata,**updates}
            for key,value in updates.items():
                changes.append({'citation_key':r.citation_key,'field':key,'before':r.input_metadata.get(key,''),'after':value,'source':r.selected_match.source_name})
        # Existing values retain LaTeX; source values are escaped to remain valid BibTeX.
        def escaped(value):
            return str(value).replace('\\','\\textbackslash{}').replace('{','\\{').replace('}','\\}').replace('&','\\&').replace('%','\\%').replace('_','\\_').replace('#','\\#')
        lines = [f'@{r.entry_type}{{{r.citation_key},']
        lines += ['  '+key+' = {'+(escaped(value) if key in updates and key != 'doi' else value)+'},' for key,value in fields.items()]
        lines.append('}')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)+'\n',changes
