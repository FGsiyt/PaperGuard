import csv
import json
from collections import Counter
from html import escape
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from .verification import bibtex

def summary(task):
    return {'task_id':task.task_id,'status':task.status,'total_references':len(task.references),'verification_status':dict(Counter(r.verification_status.value for r in task.references)),'citation_issues':len(task.findings),'metadata_mismatches':sum(f.comparison_status=='mismatch' for r in task.references for f in r.metadata_fields),'pdf_acquired':sum(bool(r.pdf_path) for r in task.references),'pdf_confirmed':sum(r.pdf_match_status=='confirmed' and bool(r.pdf_path) for r in task.references),'first_pages_extracted':sum(bool(r.first_page_path) for r in task.references),'merged_pages':task.merged_pages,'order_basis':task.order_basis,'updated_at':task.updated_at}

def export(task):
    output = Path(task.output_path)
    output.mkdir(parents=True,exist_ok=True)
    (output/'Logs').mkdir(exist_ok=True)
    data = task.model_dump(mode='json')
    data['summary'] = summary(task)
    (output/'Verification_Records.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    corrected,changes = bibtex(task)
    (output/'Corrected_References.bib').write_text(corrected,encoding='utf-8')
    approved,_ = bibtex(task,approved_only=True)
    (output/'Approved_References.bib').write_text(approved,encoding='utf-8')
    (output/'Correction_Changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'Logs'/'task.log').write_text('\n'.join([task.task_id+' '+task.status,*task.error_summary,*[r.citation_key+': '+error for r in task.references for error in r.errors]]),encoding='utf-8')
    with (output/'unresolved_references.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['citation_key','verification_status','pdf_status','pdf_match','reason'])
        for r in task.references:
            if not r.first_page_path or r.verification_status.value != 'verified':
                writer.writerow([excel_safe(r.citation_key),r.verification_status.value,r.pdf_status,r.pdf_match_status,excel_safe('; '.join(r.errors) or 'Metadata review or matched PDF still required')])
    export_html(task,output)
    export_excel(task,output)

def excel_safe(value):
    text = str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text

def export_excel(task,output):
    book = Workbook()
    book.remove(book.active)
    tables = {
        'Summary':[['Metric','Value']]+[[k,json.dumps(v,ensure_ascii=False) if isinstance(v,dict) else str(v)] for k,v in summary(task).items()],
        'References':[['Key','Title','Status','DOI','Source','Retrieved','Score']]+[[r.citation_key,r.input_metadata.get('title',''),r.verification_status.value,r.input_metadata.get('doi',''),r.selected_match.source_name if r.selected_match else '',r.selected_match.retrieved_at if r.selected_match else '',r.selected_match.score if r.selected_match else ''] for r in task.references],
        'Metadata_Differences':[['Key','Field','Input','Verified','Status','Explanation','Source']]+[[r.citation_key,f.field_name,f.input_value,f.verified_value,f.comparison_status,f.difference_explanation,f.source_name] for r in task.references for f in r.metadata_fields],
        'Citation_Issues':[['Rule','Severity','Message','Location']]+[[f.rule_id,f.severity,f.message,json.dumps(f.source_location,ensure_ascii=False)] for f in task.findings],
        'Semantic_Audit':[['Key','Label','Location','Explanation','Evidence']]+[[r.citation_key,s['label'],json.dumps(s['location'],ensure_ascii=False),s['explanation'],json.dumps(s['evidence'],ensure_ascii=False)] for r in task.references for s in r.semantic_results],
        'PDF_Status':[['Key','Status','Match','SHA256','Source','First page','Errors']]+[[r.citation_key,r.pdf_status,r.pdf_match_status,r.pdf_evidence.get('sha256',''),r.pdf_evidence.get('source_url',''),r.first_page_path,'; '.join(r.errors)] for r in task.references]
    }
    for name,rows in tables.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append([excel_safe(v)[:32000] for v in row])
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.fill = PatternFill('solid',fgColor='163C45')
            cell.font = Font(color='FFFFFF',bold=True)
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(65,max(14,max(len(str(c.value or '')) for c in column[:30])+2))
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical='top',wrap_text=True)
    book.save(output/'Reference_Metadata.xlsx')

def export_html(task,output):
    esc = lambda value:escape(str(value),quote=True)
    cards = []
    for index,r in enumerate(task.references,1):
        fields = ''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [f.field_name,f.input_value,f.verified_value,f.comparison_status,f.difference_explanation])+'</tr>' for f in r.metadata_fields)
        evidence = esc(json.dumps({'queries':r.queries,'candidates':[c.model_dump(mode='json') for c in r.candidate_matches],'pdf':r.pdf_evidence,'semantic':r.semantic_results,'errors':r.errors},ensure_ascii=False,indent=2))
        cards.append(f'<details class="ref" data-status="{r.verification_status.value}"><summary><b>[{index}] {esc(r.citation_key)}</b> · {esc(r.input_metadata.get("title",""))}<span>{r.verification_status.value}</span></summary><p>PDF: {r.pdf_status} / {r.pdf_match_status} · Semantic: {r.semantic_audit_status}</p><table><tr><th>Field</th><th>Input</th><th>Source</th><th>Status</th><th>Note</th></tr>{fields}</table><h4>Evidence / 查询与证据</h4><pre>{evidence}</pre></details>')
    issues = ''.join('<li>'+esc(f.rule_id+': '+f.message+' '+str(f.source_location))+'</li>' for f in task.findings)
    s = summary(task)
    style = 'body{font:15px system-ui;background:#f3f6f7;color:#16343b;max-width:1200px;margin:40px auto;padding:20px}h1{font-size:32px}details,.panel{background:white;border:1px solid #d7e2e4;border-radius:10px;padding:18px;margin:12px 0}summary{cursor:pointer}summary span{float:right;color:#906321}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #d7e2e4;text-align:left;padding:8px;overflow-wrap:anywhere}pre{white-space:pre-wrap;word-break:break-word;max-height:500px;overflow:auto;font-size:12px}input,select{padding:12px;border:1px solid #b7c9cc;border-radius:6px;margin-right:10px}small{color:#576d72}'
    script = "function filter(){document.querySelectorAll('.ref').forEach(e=>{e.hidden=!(e.textContent.toLowerCase().includes(document.querySelector('#q').value.toLowerCase())&&(!document.querySelector('#s').value||e.dataset.status===document.querySelector('#s').value))})}"
    options = ''.join('<option>'+state+'</option>' for state in ['verified','possible_match','metadata_mismatch','not_found','unverified','manual_review'])
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PaperGuard verification report</title><style>'+style+'</style><h1>PaperGuard · 文献核验报告</h1><small>'+esc(task.task_id+' · '+task.updated_at)+'</small><div class="panel"><b>'+str(s['total_references'])+' references · '+str(s['merged_pages'])+' merged pages</b><pre>'+esc(json.dumps(s,ensure_ascii=False,indent=2))+'</pre><p>not_found 不等于虚假文献。所有结论受数据源覆盖、网络与证据范围限制。</p></div><details><summary>引用完整性与解析问题 ('+str(len(task.findings))+')</summary><ul>'+issues+'</ul></details><input id="q" placeholder="搜索文献 / Search" oninput="filter()"><select id="s" onchange="filter()"><option value="">全部状态</option>'+options+'</select>'+''.join(cards)+'<script>'+script+'</script></html>'
    (output/'Reference_Verification_Report.html').write_text(page,encoding='utf-8')
