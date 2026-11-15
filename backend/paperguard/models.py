from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field

def now():
    return datetime.now(timezone.utc).isoformat()

class Verification(str, Enum):
    verified = 'verified'
    possible_match = 'possible_match'
    metadata_mismatch = 'metadata_mismatch'
    not_found = 'not_found'
    unverified = 'unverified'
    manual_review = 'manual_review'

class SourceRecord(BaseModel):
    source_name: str
    source_record_id: str
    query_type: str
    query_value: str
    source_url: str = ''
    retrieved_at: str = Field(default_factory=now)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    normalized_metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = 0
    match_basis: dict[str, Any] = Field(default_factory=dict)

class FieldComparison(BaseModel):
    field_name: str
    input_value: str = ''
    verified_value: str = ''
    comparison_status: Literal['match','minor_difference','mismatch','missing_in_source','missing_in_input','not_comparable']
    difference_explanation: str = ''
    source_name: str

class CitationOccurrence(BaseModel):
    citation_key: str
    source_file: str
    line_number: int
    command: str
    context_before: str = ''
    cited_text: str = ''
    context_after: str = ''
    section: str = ''

class Finding(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    rule_id: str
    category: str = 'citation'
    severity: Literal['info','warning','error'] = 'warning'
    status: Literal['open','resolved'] = 'open'
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    source_location: dict[str, Any] = Field(default_factory=dict)
    suggestion: str = ''
    confidence: float = 1
    source: str = 'PaperGuard'
    created_at: str = Field(default_factory=now)

class Reference(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    citation_key: str
    entry_type: str
    raw_bibtex: str
    input_metadata: dict[str, str]
    source_file: str
    source_line: int
    citation_locations: list[CitationOccurrence] = Field(default_factory=list)
    verification_status: Verification = Verification.unverified
    metadata_fields: list[FieldComparison] = Field(default_factory=list)
    candidate_matches: list[SourceRecord] = Field(default_factory=list)
    selected_match: SourceRecord | None = None
    queries: list[dict[str, Any]] = Field(default_factory=list)
    pdf_status: Literal['downloaded','user_uploaded','not_available','download_failed','needs_manual_review','not_attempted'] = 'not_attempted'
    pdf_path: str = ''
    first_page_path: str = ''
    pdf_match_status: Literal['confirmed','probable','mismatch','needs_manual_review'] = 'needs_manual_review'
    pdf_evidence: dict[str, Any] = Field(default_factory=dict)
    pdf_approved: bool = False
    correction_approved: bool = False
    semantic_audit_status: Literal['supported','partially_supported','unsupported','contradicted','insufficient_evidence','not_checked'] = 'not_checked'
    semantic_results: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    processed: bool = False
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)

class AuditTask(BaseModel):
    schema_version: str = '1.0'
    task_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    project_path: str
    main_tex: str | None = None
    bib_files: list[str] = Field(default_factory=list)
    status: Literal['queued','running','completed','partial','cancelled','failed','interrupted'] = 'queued'
    progress: float = 0
    current_stage: str = 'queued'
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    output_path: str = ''
    error_summary: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    input_hash: str = ''
    reference_order: list[str] = Field(default_factory=list)
    order_basis: str = ''
    merged_pages: int = 0
