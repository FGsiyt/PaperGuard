import pytest
from paperguard.parsers import parse_project,parse_bib,commands,strip_comments

def test_recursive_citations_and_bib_macros(project):
    refs,issues,order,basis,_,_,bibs = parse_project(project)
    assert [r.citation_key for r in refs] == ['alpha','beta','unused']
    assert refs[0].input_metadata['journal'] == 'Journal of Testing'
    assert 'study' in refs[1].input_metadata['title']
    assert refs[1].citation_locations[0].source_file.endswith('deep.tex')
    assert refs[0].citation_locations[0].line_number == 4
    rules = {f.rule_id for f in issues}
    assert {'missing_key','uncited_entry','order_unconfirmed'} <= rules
    assert not any('fake' in f.message for f in issues)

def test_nocite_star(project):
    with (project/'main.tex').open('a') as f:
        f.write(r'\nocite{*}')
    _,issues,*_ = parse_project(project)
    assert not any(f.rule_id=='uncited_entry' for f in issues)

def test_duplicate_keys_multiple_resources(project):
    (project/'extra.bib').write_text('@misc{alpha,title={Other}}',encoding='utf-8')
    with (project/'main.tex').open('a') as f:
        f.write(r'\addbibresource{extra.bib}')
    refs,issues,*_ = parse_project(project)
    assert len(refs)==4
    assert any(f.rule_id=='duplicate_key' for f in issues)

def test_numeric_aux_order(project):
    (project/'main.aux').write_text(r'\bibcite{beta}{1}\bibcite{alpha}{2}',encoding='utf-8')
    refs,_,_,basis,*_ = parse_project(project)
    assert [r.citation_key for r in refs][:2]==['beta','alpha']
    assert 'bibcite' in basis

def test_bbl_order(project):
    (project/'main.bbl').write_text(r'\bibitem[Chen 2021]{beta} x\bibitem{alpha} y',encoding='utf-8')
    refs,_,_,basis,*_ = parse_project(project)
    assert refs[0].citation_key=='beta' and 'bibitem' in basis

def test_comments_escapes_and_literal_macros():
    text = r"""\% literal \cite{real} % \cite{fake}
\newcommand{\mycite}[1]{\cite{#1}}
\begin{verbatim}\cite{literal}\end{verbatim}
\verb|\cite{literal2}| \cite{after}
"""
    cites = [arg for cmd,arg,_,_ in commands(strip_comments(text)) if cmd=='cite']
    assert cites==['real','after']

def test_include_cycle_and_traversal(project):
    with (project/'main.tex').open('a') as f:
        f.write(r'\input{main}\input{../outside}')
    _,issues,*_ = parse_project(project)
    assert {'include_cycle','unsafe_include'} <= {f.rule_id for f in issues}

def test_empty_and_bad_cites(project):
    with (project/'main.tex').open('a') as f:
        f.write(r'\cite{}\cite{alpha,}')
    _,issues,*_ = parse_project(project)
    assert sum(f.rule_id=='malformed_citation' for f in issues)==2

def test_broken_bib(tmp_path):
    path = tmp_path/'broken.bib'
    path.write_text('@article{bad,title={unclosed}',encoding='utf-8')
    refs,issues = parse_bib(path)
    assert not refs and issues[0].rule_id=='bib_parse_error'

def test_bib_unknown_type_raw_custom_fields(tmp_path):
    path = tmp_path/'refs.bib'
    text = '@online{key,title={Test},custom={Keep me}}'
    path.write_text(text,encoding='utf-8')
    refs,_ = parse_bib(path)
    assert refs[0].raw_bibtex == text
    assert refs[0].input_metadata['custom']=='Keep me'
