import logging
import re
from typing import Any


RELATIVE_FILE_PATTERN = re.compile(r"(%s<![A-Za-z0-9])/files/")
logger = logging.getLogger(__name__)


def absolute_lims_file_urls(value: Any, base_url: str) -> Any:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return value
    if isinstance(value, dict):
        return {key: absolute_lims_file_urls(item, base) for key, item in value.items()}
    if isinstance(value, list):
        return [absolute_lims_file_urls(item, base) for item in value]
    if isinstance(value, tuple):
        return tuple(absolute_lims_file_urls(item, base) for item in value)
    if isinstance(value, str):
        return RELATIVE_FILE_PATTERN.sub(f"{base}/files/", value)
    return value


