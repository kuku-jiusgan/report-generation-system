"""Run a small end-to-end check against a running local API."""

import json
import urllib.request
import zipfile
from pathlib import Path


BASE = "http://127.0.0.1:8010/api/v1"
ROOT = Path(__file__).resolve().parents[1]


def request(path: str, method: str = "GET", body: dict | None = None):
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=payload, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


reports = request("/reports")
report = next((item for item in reports if item["resolved_data"].get("test_items")), None)
report = report or request("/reports", "POST", {})
bindings = request(f"/reports/{report['id']}/bindings")

item = report["resolved_data"]["test_items"][0]
item["result"] = "0.35"
report = request(
    f"/reports/{report['id']}",
    "PUT",
    {"title": report["title"], "data": report["resolved_data"]},
)
history = request(f"/reports/{report['id']}/history?field_code=testItems%5Bid%3DTEST-1001%5D.result")
version = request(f"/reports/{report['id']}/versions?note=smoke-test", "POST")
generated = request(f"/reports/{report['id']}/generate", "POST")
output = ROOT / "data" / "reports" / generated["output_name"]

with zipfile.ZipFile(output) as archive:
    document_xml = archive.read("word/document.xml").decode("utf-8")

assert len(bindings) >= 10, "Expected field bindings"
assert history and history[0]["new_value"] == "0.35", "Expected saved field history"
assert version["version_no"] >= 2, "Expected a new version"
assert "0.35" in document_xml, "Expected dynamic result in exported Word"
assert "w:vMerge" in document_xml, "Expected merged category cells in exported Word"

print(json.dumps({
    "report_id": report["id"],
    "bindings": len(bindings),
    "history": len(history),
    "version": version["version_no"],
    "output": str(output),
    "merged_cells": True,
}, ensure_ascii=False, indent=2))
