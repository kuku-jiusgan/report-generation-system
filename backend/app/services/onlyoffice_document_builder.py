"""Refresh DOCX fields with ONLYOFFICE Document Builder."""

import json
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path

from .docx_field_refresher import _validated_docx, _read_parts
from .docx_language import write_docx_parts_atomic

logger = logging.getLogger(__name__)


class OnlyOfficeDocumentBuilderError(RuntimeError):
    """Raised when ONLYOFFICE cannot refresh a DOCX document."""


def _error_message(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "ONLYOFFICE 未返回错误详情").strip()


def _builder_script(input_path: str, output_path: str) -> str:
    input_literal = json.dumps(input_path)
    output_literal = json.dumps(output_path)
    return "\n".join((
        f"builderJS.OpenFile({input_literal});",
        "const oDocument = Api.GetDocument();",
        "oDocument.UpdateAllTOC(true);",
        f"builderJS.SaveFile(\"docx\", {output_literal});",
        "builderJS.CloseFile();",
        "",
    ))


def _run(command: list[str], timeout: float, *, label: str) -> None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except FileNotFoundError as error:
        raise OnlyOfficeDocumentBuilderError(
            f"ONLYOFFICE {label}不可用：找不到可执行文件“{command[0]}”"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise OnlyOfficeDocumentBuilderError(
            f"ONLYOFFICE {label}超时（{timeout:g} 秒）"
        ) from error
    except OSError as error:
        raise OnlyOfficeDocumentBuilderError(f"ONLYOFFICE {label}启动失败：{error}") from error
    if result.returncode:
        raise OnlyOfficeDocumentBuilderError(
            f"ONLYOFFICE {label}失败：{_error_message(result)}"
        )


def _copy_to_container(docker: str, container: str, source: Path, target: str,
                      timeout: float) -> None:
    _run([docker, "cp", str(source), f"{container}:{target}"], timeout, label="文件传输")


def _copy_from_container(docker: str, container: str, source: str, target: Path,
                        timeout: float) -> None:
    _run([docker, "cp", f"{container}:{source}", str(target)], timeout, label="文件传输")


def refresh_docx_fields(document_path: Path, *, container: str,
                        executable: str,
                        timeout_seconds: float = 120.0,
                        docker_executable: str = "docker") -> None:
    """Update TOC/PAGEREF fields and replace the source only after validation."""
    path = document_path.resolve()
    if not _validated_docx(path):
        raise OnlyOfficeDocumentBuilderError(f"待刷新文件不是有效的 DOCX：{path.name}")
    if timeout_seconds <= 0:
        raise OnlyOfficeDocumentBuilderError("ONLYOFFICE DOCX 域刷新超时时间必须大于 0 秒")
    if not container or not executable:
        raise OnlyOfficeDocumentBuilderError("ONLYOFFICE Document Builder 容器或可执行文件未配置")

    with tempfile.TemporaryDirectory(prefix=".onlyoffice-docbuilder-", dir=path.parent) as directory:
        workspace = Path(directory)
        input_path = workspace / path.name
        output_path = workspace / f"{path.stem}.refreshed.docx"
        script_path = workspace / "refresh_toc.js"
        write_docx_parts_atomic(_read_parts(path), input_path)
        remote_dir = f"/tmp/report-docbuilder-{uuid.uuid4().hex}"
        remote_input = f"{remote_dir}/input.docx"
        remote_output = f"{remote_dir}/output.docx"
        remote_script = f"{remote_dir}/refresh_toc.js"
        script_path.write_text(
            _builder_script(remote_input, remote_output), encoding="utf-8",
        )
        try:
            _run([docker_executable, "exec", container, "mkdir", "-p", remote_dir],
                 timeout_seconds, label="工作目录创建")
            _copy_to_container(docker_executable, container, input_path, remote_input, timeout_seconds)
            _copy_to_container(docker_executable, container, script_path, remote_script, timeout_seconds)
            _run([docker_executable, "exec", container, executable, remote_script],
                 timeout_seconds, label="目录刷新")
            _copy_from_container(docker_executable, container, remote_output, output_path, timeout_seconds)
            if not _validated_docx(output_path):
                raise OnlyOfficeDocumentBuilderError("ONLYOFFICE 未生成有效的刷新 DOCX")
            output_path.replace(path)
        finally:
            subprocess.run(
                [docker_executable, "exec", container, "rm", "-rf", remote_dir],
                capture_output=True, text=True, timeout=min(timeout_seconds, 30), check=False,
            )
    logger.info("ONLYOFFICE Document Builder 已刷新 DOCX 目录与页码 document=%s", path.name)
