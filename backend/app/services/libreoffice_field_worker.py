"""由带有 pyuno 的系统 Python 执行，不导入项目运行环境。"""

import sys
import time
from pathlib import Path

import uno


def _property(name: str, value: object):
    item = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    item.Name = name
    item.Value = value
    return item


def _connect(pipe_name: str, timeout_seconds: float):
    local_context = uno.getComponentContext()
    resolver = local_context.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_context,
    )
    deadline = time.monotonic() + timeout_seconds
    connection = f"uno:pipe,name={pipe_name};urp;StarOffice.ComponentContext"
    while True:
        try:
            return resolver.resolve(connection)
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError("连接 LibreOffice 排版服务超时")
            time.sleep(0.1)


def _update_indexes(document) -> None:
    indexes = document.getDocumentIndexes()
    for index in range(indexes.getCount()):
        indexes.getByIndex(index).update()


def refresh_fields(pipe_name: str, source: Path, output: Path,
                   timeout_seconds: float) -> None:
    context = _connect(pipe_name, min(timeout_seconds, 30.0))
    desktop = context.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", context,
    )
    document = None
    try:
        document = desktop.loadComponentFromURL(
            uno.systemPathToFileUrl(str(source.resolve())),
            "_blank",
            0,
            (_property("Hidden", True), _property("ReadOnly", False)),
        )
        if document is None:
            raise RuntimeError("LibreOffice 无法打开 DOCX")
        text_fields = document.getTextFields()
        for _ in range(3):
            _update_indexes(document)
            if text_fields is not None:
                text_fields.refresh()
        document.storeAsURL(
            uno.systemPathToFileUrl(str(output.resolve())),
            (
                _property("FilterName", "Office Open XML Text"),
                _property("Overwrite", True),
            ),
        )
    finally:
        if document is not None:
            document.close(True)
        desktop.terminate()


def main() -> int:
    if len(sys.argv) != 5:
        print("用法：libreoffice_field_worker.py PIPE INPUT OUTPUT TIMEOUT", file=sys.stderr)
        return 2
    try:
        refresh_fields(
            sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), float(sys.argv[4]),
        )
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
