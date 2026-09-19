from typing import Any

from fastapi import APIRouter

from ..services.lims_rule_schema import lims_rule_metadata


def register_lims_rule_routes(router: APIRouter) -> None:
    @router.get("/lims-rule-metadata")
    def rule_metadata() -> dict[str, Any]:
        return lims_rule_metadata()
