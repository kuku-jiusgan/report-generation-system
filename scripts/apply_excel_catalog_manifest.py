"""Apply an Excel catalog manifest after reviewing its field and rule diff."""

import argparse
from pathlib import Path

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.services.excel_catalog_manifest import apply_manifest, prepared_fields, read_manifest
from backend.app.services.system_field_groups import list_system_field_groups
from backend.app.services.rule_admin import RuleAdminRepository
from backend.app.services.segment_table_install import apply_segment_table


def main() -> None:
    parser = argparse.ArgumentParser(description="查看或安装 Excel 字段目录清单")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true", help="实际写入字段目录和 Excel 来源规则")
    parser.add_argument("--apply-template", action="store_true", help="给当前草稿安装原版式行片段表配置")
    args = parser.parse_args()
    manifest = read_manifest(args.manifest)
    database = Database(Settings())
    group = next((item for item in list_system_field_groups(database)
                  if item["groupCode"] == manifest["groupCode"]), None)
    if group is None:
        raise ValueError("指定编组不存在")
    for field in prepared_fields(manifest, group):
        print(f"{field['fieldCode']}: {field['legacyJsonPath']}")
    if args.apply:
        print(f"已安装 {len(apply_manifest(database, manifest))} 条 Excel 字段提取配置")
    else:
        print("当前为只读预览；添加 --apply 后才写入数据库")
    if args.apply_template:
        if not args.apply:
            raise ValueError("安装模板表格前须同时执行 --apply")
        repository = RuleAdminRepository(database, Path("mapping/template-mapping.json"))
        print(f"已配置当前草稿 Word 表格 {manifest['tableNo']}，物理表格序号 "
              f"{apply_segment_table(repository, manifest)}")


if __name__ == "__main__":
    main()
