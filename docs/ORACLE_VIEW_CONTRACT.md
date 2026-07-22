# Oracle LIMS 只读视图契约

生产连接账号只授予 `SELECT` 权限，业务服务只能查询配置白名单中的视图。禁止接收客户端传入的表名、列名或 SQL 片段。

首版建议由 LIMS 提供视图 `V_CRO_REPORT_SOURCE`：

| 列 | 类型 | 说明 |
| --- | --- | --- |
| PROJECT_NO | VARCHAR2(64) | 项目编号，查询条件 |
| SAMPLE_NO | VARCHAR2(64) | 样品编号，查询条件 |
| EXPERIMENT_NO | VARCHAR2(64) | 实验编号，查询条件 |
| PROJECT_NAME | VARCHAR2(500) | 项目名称 |
| SAMPLE_NAME | VARCHAR2(500) | 样品名称 |
| BATCH_NO | VARCHAR2(128) | 样品批号 |
| METHOD_NO | VARCHAR2(128) | 方法编号 |
| ANALYST_NAME | VARCHAR2(128) | 实验人员 |
| ANALYSIS_DATE | TIMESTAMP | 实验日期 |

查询必须同时使用项目、样品和实验编号的绑定参数，并限制最多返回两行。零行标记为缺失，多行标记为冲突，不自动选择任意一行。

