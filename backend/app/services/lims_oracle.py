from typing import Any

import oracledb

from ..config import Settings
from .lims_parser import parse_lims_query_rows, parse_lims_rows


LIMS_PROJECT_SQL = """
SELECT * FROM sdzb.T_CORE_LES_INSTANCE_UNIT a
LEFT JOIN sdzb.T_CORE_LES_INSTANCE b ON a.INSTANCEID = b.id
WHERE b.projectid = :project_id
"""


def query_lims_project(settings: Settings, project_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not settings.lims_sql_enabled:
        raise RuntimeError("当前环境未启用 LIMS SQL 查询")
    if not all((settings.lims_sql_dsn.strip(), settings.lims_sql_user.strip(), settings.lims_sql_password)):
        raise RuntimeError("LIMS Oracle 连接信息未配置完整")

    connection = oracledb.connect(
        user=settings.lims_sql_user,
        password=settings.lims_sql_password,
        dsn=settings.lims_sql_dsn,
        tcp_connect_timeout=settings.lims_sql_connect_timeout,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(LIMS_PROJECT_SQL, project_id=project_id)
            headers = [column[0] for column in cursor.description or []]
            query_values = [
                tuple(value.read() if isinstance(value, oracledb.LOB) else value for value in row)
                for row in cursor.fetchall()
            ]
            rows = parse_lims_query_rows(headers, query_values)
            source_ids = sorted({str(row["source_id"]) for row in rows if row.get("source_id")})
            names_by_source: dict[str, str] = {}
            if source_ids:
                binds = {f"source_{index}": value for index, value in enumerate(source_ids)}
                placeholders = ",".join(f":{name}" for name in binds)
                cursor.execute(
                    f"SELECT U_DEPTEPTID, EPTNAME FROM sdzb.U_DEPTEPT "
                    f"WHERE U_DEPTEPTID IN ({placeholders})",
                    **binds,
                )
                names_by_source = {
                    str(source_id): str(name or "").strip()
                    for source_id, name in cursor.fetchall()
                }
    finally:
        connection.close()

    summary = parse_lims_rows(rows, file_base_url=settings.lims_file_base_url)
    instances = [parse_lims_rows(rows, item["instanceId"], settings.lims_file_base_url)
                 for item in summary["instances"]]
    for instance in instances:
        source_id = next(
            (str(row["source_id"]) for row in rows
             if row["instance_id"] == instance["instanceId"] and row.get("source_id")),
            "",
        )
        source_name = names_by_source.get(source_id, "")
        if source_name:
            instance["title"] = source_name
            instance["project"]["name"] = source_name
    titles = {item["instanceId"]: item["title"] for item in instances}
    for item in summary["instances"]:
        item["title"] = titles.get(item["instanceId"], item["title"])
    return summary, instances
