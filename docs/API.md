# API 摘要

所有业务接口默认使用 HTTP Basic 演示认证。生产部署应将 `SecurityConfig` 替换为公司 LDAP/OIDC 适配器。

- `POST /api/reports`: 创建报告任务。
- `GET /api/reports/{id}`: 查询报告、字段和证据。
- `POST /api/reports/{id}/extract`: 冻结来源并执行规则。
- `POST /api/reports/{id}/generate`: 校验通过后创建不可覆盖版本。
- `GET /api/reports/{id}/editor-config`: 获取 ONLYOFFICE JWT 配置。
- `POST /api/integrations/onlyoffice/callback`: 接收编辑器保存回调。
- `POST /v1/extract`: 文档服务确定性提取接口。
- `POST /v1/templates/scan`: 扫描内容控件及重复标签。
- `POST /v1/documents/fill`: 填充内容控件并执行可选渲染检查。

演示账号只用于本地：`admin/admin-change-me`、`analyst/analyst-change-me`、`viewer/viewer-change-me`。生产启动前必须删除。

