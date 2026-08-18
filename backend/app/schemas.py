from typing import Any

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    type: str
    record_id: str | None = None
    document_id: str | None = None
    page: int | None = None
    quote: str | None = None
    rect: list[float] | None = None


class ExtractedField(BaseModel):
    field_code: str
    label: str
    value: str
    confidence: float = Field(ge=0, le=1)
    source: SourceRef


class SourceDocument(BaseModel):
    id: str
    file_name: str
    size: int
    preview_url: str
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    source_type: str = "PDF"
    warnings: list[str] = Field(default_factory=list)
    sha256: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class TestItem(BaseModel):
    id: str
    category: str = ""
    name: str = ""
    method: str = ""
    requirement: str = ""
    result: str = ""
    unit: str = ""
    conclusion: str = ""


class ReportData(BaseModel):
    report_no: str = ""
    customer: str = ""
    sample: str = ""
    project_name: str = ""
    report_date: str = ""
    conclusion: str = ""
    author: str = ""
    reviewer: str = ""
    approver: str = ""
    template_version: str = "V1.0"
    template_id: str = ""
    template_name: str = ""
    template_code: str = ""
    template_catalog_version_id: str = ""
    template_revision: str = ""
    test_items: list[TestItem] = Field(default_factory=list)
    field_sources: dict[str, SourceRef] = Field(default_factory=dict)
    original_values: dict[str, Any] = Field(default_factory=dict)
    source_payloads: dict[str, dict] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ApplyLimsRequest(BaseModel):
    import_id: str
    instance_ids: list[str] = Field(min_length=1)
    conflict_resolutions: dict[str, str] = Field(default_factory=dict)
    force: bool = False


class RecognizeLimsRequest(BaseModel):
    instance_ids: list[str] = Field(min_length=1)


class QueryLimsRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


class CreateReportRequest(BaseModel):
    title: str | None = None
    source_document_id: str | None = None
    excel_document_id: str | None = None
    data: ReportData | None = None


class UpdateReportRequest(BaseModel):
    title: str | None = None
    data: ReportData


class ReplaceSourceRequest(BaseModel):
    source_document_id: str = Field(min_length=1)
    source_type: str = Field(pattern=r"^(PDF|EXCEL)$")


class ReportTask(BaseModel):
    id: str
    title: str
    status: str
    source_document_id: str | None = None
    resolved_data: ReportData
    output_name: str | None = None
    download_url: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    word_edit_locked: bool = False
    word_edited_at: str | None = None
    created_at: str
    updated_at: str


class FieldBinding(BaseModel):
    field_code: str
    label: str
    current_value: str
    original_value: str
    source: SourceRef
    modified: bool


class ChangeEvent(BaseModel):
    id: int
    report_id: str
    field_code: str
    old_value: str
    new_value: str
    operator: str
    reason: str
    created_at: str


class ReportVersion(BaseModel):
    id: int
    report_id: str
    version_no: int
    note: str
    created_at: str
    data: ReportData
