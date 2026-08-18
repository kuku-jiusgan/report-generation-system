"""Canonical mapping between template fields and resolved report data."""

REPORT_FIELD_BINDINGS = {
    "project.name": "project_name",
    "project.name.body": "project_name",
    "document.code": "report_no",
    "reportHeader.reportNo": "report_no",
    "reportHeader.customer": "customer",
    "reportHeader.sample": "sample",
    "reportHeader.conclusion": "conclusion",
}


def report_binding_code(field_code: str) -> str:
    """Return the resolved report field consumed by the editor and generator."""
    return REPORT_FIELD_BINDINGS.get(field_code, field_code)
