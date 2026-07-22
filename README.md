# CRO 基因毒杂质验证报告系统

面向内网部署的首版单仓库，实现 LIMS/PDF 数据取证、规则校验、DOCX 内容控件填充、在线编辑接入和版本化导出。

## 目录

- `frontend/`: React + TypeScript + Fluent UI 工作台与后台
- `backend/`: Spring Boot 业务 API、版本、审计和适配器
- `document-service/`: FastAPI PDF 解析、规则执行和 OOXML 填充
- `infra/`: PostgreSQL 初始化与 Nginx 配置

## 本地演示

前端包含完整模拟数据，即使没有 Oracle、MinIO 和 ONLYOFFICE 也能查看所有主要界面。

```powershell
cd frontend
pnpm install
pnpm dev
```

打开 `http://localhost:5173`。默认 API 地址为 `http://localhost:8080`，连接失败时自动使用演示数据。

Windows 本机模式准备好便携运行时后，可使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
# 停止
powershell -ExecutionPolicy Bypass -File scripts\stop-local.ps1
```

本机模式端口：前端 `5173`、文档服务 `8001`、Spring Boot `8080`。如果系统的 `8000` 已被其他程序占用，不会终止该程序。

完整环境：复制 `.env.example` 为 `.env`，然后运行 `docker compose up --build`。生产前必须替换所有示例密钥、限制网络入口，并确认 ONLYOFFICE 授权和并发数。

## 真实数据接入

1. 在 Oracle 建立只读视图及专用账号，只允许白名单视图。
2. 在后台上传带 Word 内容控件的 DOCX，标签必须与规则的 `targetControlTag` 唯一对应。
3. 为仪器 PDF 建立确定性规则：文字锚点、正则、页码或坐标区域。
4. 用至少 20 份脱敏历史样本建立黄金样本集，再发布模板和规则。

系统不会猜测缺失或冲突数据。必填字段异常时，生成版本被标记为 `BLOCKED`，但原始证据仍可查看。
