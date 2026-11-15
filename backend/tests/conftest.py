from pathlib import Path
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
from paperguard.config import Settings
from paperguard.storage import Store
from paperguard.models import SourceRecord

@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path/'data',sources=('crossref','openalex'),timeout=3)

@pytest.fixture
def store(settings):
    return Store(settings.data_dir)

@pytest.fixture
def project(tmp_path):
    root = tmp_path/'project'
    (root/'sections').mkdir(parents=True)
    (root/'main.tex').write_text(r"""\documentclass{article}
\begin{document}
\section{Intro}
Work \cite[p. 3]{alpha, missing}.
% \cite{fake}
\input{sections/method}
\bibliography{refs}
\end{document}
""",encoding='utf-8')
    (root/'sections'/'method.tex').write_text(r'\include{sections/deep}',encoding='utf-8')
    # TeX inputs are normally resolved relative to the project root; support nested local files too.
    (root/'sections'/'method.tex').write_text(r'\include{deep}',encoding='utf-8')
    (root/'sections'/'deep.tex').write_text(r'\subsection{Method} More \citep{beta}.',encoding='utf-8')
    (root/'refs.bib').write_text(r"""@string{venue = "Journal of Testing"}
@article{alpha,title={A reliable test paper},author={Smith, Alice and Jones, Bob},year={2020},doi={10.1234/test-alpha},journal=venue}
@article{beta,title={Nested {Title} } # "study",author={Chen, C},year={2021}}
@misc{unused,title={Uncited fixture},year=2022}
""",encoding='utf-8')
    return root

@pytest.fixture
def candidate():
    return SourceRecord(source_name='fixture-crossref',source_record_id='10.1234/test-alpha',query_type='doi',query_value='10.1234/test-alpha',source_url='https://example.org/fixture',normalized_metadata={'title':'A reliable test paper','author':'Smith, Alice and Jones, Bob','year':'2020','doi':'10.1234/test-alpha','journal':'Journal of Testing','oa_locations':[]},raw_metadata={'fixture_only':True})

def make_pdf(path,text='A reliable test paper\nAlice Smith and Bob Jones\n10.1234/test-alpha',sizes=((612,792),(500,700))):
    writer = PdfWriter()
    for index,(width,height) in enumerate(sizes):
        page = writer.add_blank_page(width=width,height=height)
        font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        escaped = (text if index == 0 else 'SECOND PAGE MUST NOT BE MERGED').replace('\\','\\\\').replace('(','\\(').replace(')','\\)').replace('\n',') Tj 0 -20 Td (')
        stream = DecodedStreamObject()
        stream.set_data(('BT /F1 12 Tf 40 '+str(height-60)+' Td ('+escaped+') Tj ET').encode('latin-1'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    with Path(path).open('wb') as f:
        writer.write(f)
    return Path(path)
