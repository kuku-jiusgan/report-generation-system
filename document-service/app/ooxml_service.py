import hashlib, io, os, shutil, subprocess, tempfile, zipfile
from pathlib import Path
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
PATCHABLE = ("word/document.xml",)

def _patchable_names(names: list[str]) -> list[str]:
    return [n for n in names if n in PATCHABLE or n.startswith("word/header") and n.endswith(".xml") or n.startswith("word/footer") and n.endswith(".xml")]

def scan_controls(path: Path) -> dict:
    found: list[dict] = []
    with zipfile.ZipFile(path) as z:
        for name in _patchable_names(z.namelist()):
            root = etree.fromstring(z.read(name))
            for sdt in root.xpath(".//w:sdt", namespaces=NS):
                tags = sdt.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
                aliases = sdt.xpath("./w:sdtPr/w:alias/@w:val", namespaces=NS)
                text = "".join(sdt.xpath(".//w:sdtContent//w:t/text()", namespaces=NS))
                if tags: found.append({"tag": tags[0], "alias": aliases[0] if aliases else None, "text": text, "part": name})
    tags = [x["tag"] for x in found]
    duplicates = sorted({x for x in tags if tags.count(x) > 1})
    return {"controls": found, "count": len(found), "duplicates": duplicates, "valid": bool(found) and not duplicates}

def fill_controls(source: Path, target: Path, values: dict[str,str], required: list[str]) -> dict:
    scan = scan_controls(source)
    present = {x["tag"] for x in scan["controls"]}
    missing_required = sorted(set(required) - present)
    if scan["duplicates"] or missing_required:
        raise ValueError(f"Template control validation failed; duplicates={scan['duplicates']}, missing={missing_required}")
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename in _patchable_names(src.namelist()):
                root = etree.fromstring(data)
                for sdt in root.xpath(".//w:sdt",namespaces=NS):
                    tags=sdt.xpath("./w:sdtPr/w:tag/@w:val",namespaces=NS)
                    if not tags or tags[0] not in values: continue
                    content=sdt.find(f"{{{W}}}sdtContent")
                    texts=content.xpath(".//w:t",namespaces=NS) if content is not None else []
                    if not texts: continue
                    texts[0].text=str(values[tags[0]])
                    for node in texts[1:]: node.text=""
                data=etree.tostring(root,xml_declaration=True,encoding="UTF-8",standalone=True)
            out.writestr(item,data)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    return {"sha256":digest,"filledTags":sorted(set(values)&present),"unmappedTags":sorted(set(values)-present),"structure":scan}

def render_check(docx: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True,exist_ok=True)
    soffice=shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice: return {"available":False,"passed":False,"reason":"LibreOffice not installed"}
    with tempfile.TemporaryDirectory() as profile:
        cmd=[soffice,"--headless",f"-env:UserInstallation=file:///{profile.replace(os.sep,'/')}","--convert-to","pdf","--outdir",str(output_dir),str(docx)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    pdf=output_dir/(docx.stem+".pdf")
    return {"available":True,"passed":result.returncode==0 and pdf.exists() and pdf.stat().st_size>0,"pdf":str(pdf) if pdf.exists() else None,"log":(result.stdout+result.stderr)[-2000:]}

