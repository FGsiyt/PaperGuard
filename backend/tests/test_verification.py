import pytest
from paperguard.verification import classify,comparisons,suggested_fields,bibtex
from paperguard.normalization import norm,authors_match,venue_equivalent
from paperguard.models import Reference,AuditTask

META = {'title':'A reliable test paper','author':'Smith, Alice and Jones, Bob','year':'2020','doi':'10.1234/test-alpha','journal':'Journal of Testing'}
Q = [{'status':'ok','source':'fixture'}]

def test_exact_doi(candidate):
    status,selected,fields = classify(META,[candidate],Q)
    assert status.value=='verified'
    assert selected.match_basis['doi_exact']
    assert all(f.comparison_status in {'match','not_comparable'} for f in fields)

def test_wrong_doi_not_rewritten(candidate):
    wrong = {**META,'title':'An entirely unrelated study','author':'Nobody, N'}
    status,selected,fields = classify(wrong,[candidate],Q)
    assert status.value=='metadata_mismatch'
    ref = Reference(citation_key='bad',entry_type='article',raw_bibtex='',input_metadata=wrong,source_file='',source_line=1,selected_match=selected,verification_status=status,metadata_fields=fields)
    assert suggested_fields(ref)=={}

@pytest.mark.parametrize('changes',[{'title':'A reliable test papre'},{'author':'Jones, Bob and Smith, Alice'},{'year':'2021'}])
def test_metadata_differences(candidate,changes):
    status,selected,fields = classify({**META,**changes},[candidate],Q)
    assert status.value=='metadata_mismatch'
    assert any(f.field_name in changes and f.comparison_status=='mismatch' for f in fields)

def test_title_author_year_without_doi(candidate):
    m = {k:v for k,v in META.items() if k!='doi'}
    status,_,_ = classify(m,[candidate],Q)
    assert status.value=='verified'

def test_title_alone_is_not_identity(candidate):
    status,_,_ = classify({'title':META['title']},[candidate],Q)
    assert status.value=='possible_match'

@pytest.mark.parametrize('queries,expected',[(Q,'not_found'),([{'status':'error'}],'unverified'),([],'unverified')])
def test_not_found_is_not_network_failure(queries,expected):
    assert classify(META,[],queries)[0].value==expected

def test_conflicting_sources(candidate):
    other = candidate.model_copy(deep=True)
    other.normalized_metadata['doi']='10.1234/different'
    assert classify(META,[candidate,other],Q)[0].value=='manual_review'

def test_publication_stage_year(candidate):
    candidate.normalized_metadata['publication_years']={'published-online':'2019','published-print':'2020'}
    fields = comparisons({**META,'year':'2019'},candidate)
    year = next(f for f in fields if f.field_name=='year')
    assert year.comparison_status=='minor_difference'

def test_normalization_abbreviations():
    assert norm(r'{Caf\"e} &amp; Tests') == 'cafe tests'
    assert authors_match('Smith, A and Jones, B','Alice Smith and Bob Jones')
    assert not authors_match('Smith, A and Jones, B','Bob Jones and Alice Smith')
    assert venue_equivalent('Journal of Testing','JT') is False  # two-letter abbreviations ambiguous
    assert venue_equivalent('IEEE Transactions on Wireless Communications','ITWC')

def test_corrections_preserve_keys_custom_fields(candidate):
    status,selected,fields = classify({**META,'volume':'wrong'},[candidate],Q)
    selected.normalized_metadata['volume']='7'
    fields = comparisons({**META,'volume':'wrong','custom':'keep'},selected)
    r = Reference(citation_key='keep_key',entry_type='article',raw_bibtex='',input_metadata={**META,'volume':'wrong','custom':'keep'},source_file='',source_line=1,verification_status=status,selected_match=selected,metadata_fields=fields)
    task = AuditTask(project_path='.',references=[r])
    output,changes = bibtex(task)
    assert '@article{keep_key' in output and 'custom = {keep}' in output
    assert 'volume = {7}' in output and changes[0]['field']=='volume'
    approved,_ = bibtex(task,approved_only=True)
    assert 'volume = {wrong}' in approved
