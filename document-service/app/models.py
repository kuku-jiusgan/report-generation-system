from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

class SourceType(str, Enum):
    ORACLE = "ORACLE"
    PDF = "PDF"

class Locator(BaseModel):
    kind: Literal["regex", "anchor_regex", "bbox", "oracle_column"]
    pattern: str | None = None
    anchor: str | None = None
    page_from: int = Field(default=1, ge=1)
    page_to: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    column: str | None = None

class Transformer(BaseModel):
    trim: bool = True
    decimals: int | None = Field(default=None, ge=0, le=12)
    unit_pattern: str | None = None
    enum: dict[str, str] = Field(default_factory=dict)

class Validator(BaseModel):
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None

class ExtractionRule(BaseModel):
    fieldCode: str
    label: str
    sourceType: SourceType
    locator: Locator
    transformer: Transformer = Field(default_factory=Transformer)
    validator: Validator = Field(default_factory=Validator)
    targetControlTag: str
    onMissing: Literal["BLOCK", "WARN"] = "BLOCK"
    evidencePolicy: Literal["FULL", "LOCATION_ONLY"] = "FULL"

    @model_validator(mode="after")
    def source_matches_locator(self):
        if self.sourceType == SourceType.ORACLE and self.locator.kind != "oracle_column":
            raise ValueError("ORACLE rules require oracle_column locator")
        if self.sourceType == SourceType.PDF and self.locator.kind == "oracle_column":
            raise ValueError("PDF rules cannot use oracle_column locator")
        return self

class Evidence(BaseModel):
    sourceType: SourceType
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    source: str
    excerpt: str | None = None

class FieldResult(BaseModel):
    fieldCode: str
    label: str
    rawValue: str | None
    normalizedValue: str | None
    status: Literal["VALID", "MISSING", "CONFLICT", "WARNING"]
    targetControlTag: str
    evidence: Evidence
    errors: list[str] = Field(default_factory=list)

class ExtractResponse(BaseModel):
    sha256: str
    pageCount: int
    status: Literal["VALID", "BLOCKED"]
    fields: list[FieldResult]

class FillRequest(BaseModel):
    values: dict[str, str]
    requiredTags: list[str] = Field(default_factory=list)

