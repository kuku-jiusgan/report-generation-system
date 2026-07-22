import json, tempfile, uuid
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from .models import ExtractionRule, FillRequest
from .pdf_service import extract
from .ooxml_service import scan_controls, fill_controls, render_check

app=FastAPI(title="CRO deterministic extraction and OOXML service",version="0.1.0")
ROOT=Path(__import__("os").environ.get("STORAGE_ROOT",tempfile.gettempdir()))/"cro-doc-service"
ROOT.mkdir(parents=True,exist_ok=True)

@app.get("/health")
def health(): return {"status":"UP","mode":"deterministic"}

async def save_upload(file: UploadFile, suffix: str) -> Path:
    path=ROOT/f"{uuid.uuid4()}{suffix}"
    content=await file.read()
    path.write_bytes(content)
    return path

@app.post("/v1/extract")
async def extract_endpoint(pdf: UploadFile=File(...),rules_json:str=Form(...),oracle_json:str=Form("{}")):
    path=await save_upload(pdf,".pdf")
    try:
        rules=[ExtractionRule.model_validate(x) for x in json.loads(rules_json)]
        return extract(path,rules,json.loads(oracle_json))
    except (ValueError,json.JSONDecodeError) as exc: raise HTTPException(422,str(exc)) from exc

@app.post("/v1/templates/scan")
async def scan_template(template:UploadFile=File(...)):
    path=await save_upload(template,".docx")
    try:return scan_controls(path)
    except Exception as exc:raise HTTPException(422,"Invalid DOCX package") from exc

@app.post("/v1/documents/fill")
async def fill_document(request_json:str=Form(...),template:UploadFile=File(...),render:bool=Form(True)):
    source=await save_upload(template,".docx"); target=ROOT/f"{uuid.uuid4()}-filled.docx"
    try:
        request=FillRequest.model_validate_json(request_json)
        metadata=fill_controls(source,target,request.values,request.requiredTags)
        if render: metadata["renderCheck"]=render_check(target,ROOT/f"render-{target.stem}")
        headers={"X-Document-Metadata":json.dumps(metadata,ensure_ascii=True,separators=(",",":"))}
        return FileResponse(target,media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",filename="generated-report.docx",headers=headers)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc

