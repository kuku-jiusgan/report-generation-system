# 报告自动生成系统

面向单台 Windows 或 Linux 服务器的报告生成应用。前端使用 Vue 3，后端使用 FastAPI；业务数据保存到 SQLite，上传文件和生成报告保存在本机 `data` 目录，不依赖 Docker、MinIO 或外部数据库。

## 当前功能

- 相互独立的报告生成端与后台管理端，使用本地账号和角色权限登录
- 用户管理、角色权限矩阵以及不可覆盖的报告生成历史
- 三栏式报告编制工作台：数据源、在线文档、字段证据
- LIMS、PDF、人工录入三类字段来源及颜色标识
- 字段原始值、当前值、PDF 原文证据和修改历史
- Word 风格在线编辑与基础文字格式工具
- 动态检测结果表格、行增删和分类单元格纵向合并
- 保存草稿、报告版本、PDF 预览和 Word 导出
- 上传、保存和在线预览 PDF
- 从文字型 PDF 提取报告编号、客户名称和样品名称
- 使用现有 Word 模板内容控件生成 DOCX

## Windows 首次运行

在 PowerShell 中执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd "E:\报告自动生成系统"
.\scripts\setup.ps1
.\start.ps1
```

安装脚本会把 Python 和 Node.js 下载到项目内的 `.tools` 目录，创建 `.venv`，安装依赖并构建 Vue。它不会安装 Docker，也不会修改系统级 PATH。

报告生成端：`http://127.0.0.1:8010/`

后台管理端：`http://127.0.0.1:8010/admin/`

首次启动会提示设置超级管理员账号和密码，首次登录后必须修改密码。也可以提前设置环境变量 `REPORT_BOOTSTRAP_ADMIN_USERNAME` 和 `REPORT_BOOTSTRAP_ADMIN_PASSWORD`。

API 文档：`http://127.0.0.1:8010/docs`

当前 Windows 本机已接入原生安装的 ONLYOFFICE Document Server，默认通过 `http://127.0.0.1:8088` 加载真实 DOCX 在线编辑器。字段来源视图仍保留，用于查看颜色、来源证据和结构化数据。启动脚本会自动读取 ONLYOFFICE 安装器生成的 JWT 密钥，不把密钥写入项目源码。

本机端口分配：

```text
http://127.0.0.1:8010  报告工作台与 Python API
http://127.0.0.1:8088  ONLYOFFICE Document Server
```

ONLYOFFICE 在 Windows 上还会占用内部端口 `8000`，因此报告系统不能再使用该端口。

## 日常启动

```powershell
cd "E:\报告自动生成系统"
.\start.ps1
```

按 `Ctrl+C` 停止服务。开发前端时可以运行 `.\start-dev.ps1`，访问 `http://127.0.0.1:5173`。

需要让同一局域网内的其他电脑访问时运行：

```powershell
.\start.ps1 -HostAddress 0.0.0.0 -Port 8010
```

同时需要在 Windows 防火墙中允许 TCP 8010 端口，仅对可信局域网开放。

## 数据与备份

```text
data/report-system.db  报告业务数据
data/uploads/          上传的 PDF
data/reports/          生成的 Word 文件
templates/             报告模板
mapping/               模板字段映射
```

备份时停止服务，然后复制整个 `data`、`templates` 和 `mapping` 目录。建议每天定时备份到另一块磁盘或 NAS，并设置备份保留周期。

## Linux 部署

源码不使用 Windows 专属 API。Linux 上安装 Python 3.12 和 Node.js LTS 后，创建虚拟环境、安装 `backend/requirements.txt`、构建 `frontend`，再用 Uvicorn 启动即可。当前使用 SQLite，生产环境建议先以 `uvicorn app.main:app --host 127.0.0.1 --port 8010 --app-dir backend` 单进程运行，并通过 Nginx 提供 HTTPS；`data` 目录应挂载到独立数据盘。后续迁移到 PostgreSQL 后，再根据并发量增加 Uvicorn 工作进程。
