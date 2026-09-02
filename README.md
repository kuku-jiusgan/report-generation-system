# 报告自动生成系统

面向单台 Windows 或 Linux 服务器的报告生成应用。前端使用 Vue 3，后端使用 FastAPI；业务数据保存到本机 MySQL，上传文件和生成报告保存在本机 `data` 目录。

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

## Linux 首次运行

需要 Python 3.11+、Node.js 20+、npm、Docker 和 Docker Compose。先安装项目依赖：

```bash
cd /home/zoutengda/report-generation-system
./scripts/setup.sh
```

安装脚本会创建项目内的 `.venv`、安装前后端依赖并构建 Vue，不会修改系统级 Python 或 Node.js。

首次启动前编辑 `.env`。`SERVER_IP` 表示运行本项目的 Linux 服务器地址，请在文件中写实际 IP，不要原样填写变量名：

```dotenv
REPORT_BOOTSTRAP_ADMIN_USERNAME=admin
REPORT_BOOTSTRAP_ADMIN_PASSWORD=请设置至少8位的初始密码
REPORT_ONLYOFFICE_URL=http://SERVER_IP:8090
REPORT_ONLYOFFICE_JWT_SECRET=请设置一个足够长的随机密钥
REPORT_PUBLIC_BASE_URL=http://SERVER_IP:8010
```

LIMS 使用 Oracle 时，在 `.env` 中另外配置以下变量。DSN 建议使用 Oracle Easy Connect 格式 `主机:端口/服务名`：

```dotenv
REPORT_LIMS_SQL_ENABLED=true
REPORT_LIMS_SQL_DSN=192.168.2.16:1521/请填写Oracle服务名
REPORT_LIMS_SQL_USER=read
REPORT_LIMS_SQL_PASSWORD=请填写密码
```

报告端只接收项目编号，后端使用绑定变量执行固定 SQL，不接收前端传入的 SQL 文本。

`REPORT_ONLYOFFICE_JWT_SECRET` 必须与 Docker 容器使用同一个值；Compose 会直接读取此 `.env` 文件。请将两处 `SERVER_IP` 都替换为服务器实际 IP，这样浏览器可以加载编辑器，容器也可以回调报告服务。不要把 `REPORT_PUBLIC_BASE_URL` 写成 `127.0.0.1`，因为容器中的该地址指向容器自身，而不是宿主机。

项目已经提供 [docker-compose.onlyoffice.yml](docker-compose.onlyoffice.yml)，用于运行独立的 ONLYOFFICE Document Server。`start.sh` 是统一启动入口，会先启动或检查 ONLYOFFICE 容器，再启动报告系统：

```bash
./start.sh
```

首次运行会下载较大的 ONLYOFFICE 镜像并可能要求输入 `sudo` 密码，初始化可能需要几分钟。脚本会等待 Compose 启动命令成功后再启动报告系统；宿主机端口分别为 `8090` 和 `8010`。

容器名为 `report-system-onlyoffice`。启动后访问：

```text
http://SERVER_IP:8010/        报告生成端
http://SERVER_IP:8010/admin/  后台管理端
http://SERVER_IP:8010/docs    API 文档
http://SERVER_IP:8090/        ONLYOFFICE Document Server
```

首次管理员登录后必须立即修改密码。

## Linux 日常启动与停止

正式部署推荐安装 systemd 服务。它会自动启动 ONLYOFFICE、在后台守护报告系统、进程退出后自动重启，并随服务器开机启动。健康检查每分钟访问一次 `/health`，服务未运行、端口不通或接口异常时会自动重启：

```bash
sudo ./scripts/install-service.sh
```

安装后不需要保持终端打开。常用管理命令：

```bash
sudo systemctl status report-generation.service
sudo systemctl status report-generation-healthcheck.timer
sudo systemctl restart report-generation.service
sudo systemctl stop report-generation.service
sudo journalctl -u report-generation.service -f
```

服务名为 `report-generation.service`，监听器为 `report-generation-healthcheck.timer`。启动时会先通过 [docker-compose.onlyoffice.yml](docker-compose.onlyoffice.yml) 启动 `report-system-onlyoffice`，再启动 `0.0.0.0:8010` 上的报告系统。监听器启用期间，即使手动停止主服务也会在下一次检查时重新启动；维护时应先停止监听器。配置了 `restart: unless-stopped` 的 ONLYOFFICE 容器会继续运行。

不安装 systemd、仅临时运行时仍可使用统一启动命令：

```bash
./start.sh
```

临时运行依赖当前终端，按 `Ctrl+C` 会停止报告系统。只允许本机访问时运行 `./start.sh --host 127.0.0.1 --port 8010`。开发模式运行 `./start-dev.sh`。

依赖下载需要代理时，可以在安装命令前设置标准代理环境变量，例如：

```bash
HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897 ./scripts/setup.sh
```

如果不使用项目提供的 Docker 服务，而是在 Linux 原生安装 ONLYOFFICE Document Server，系统会自动读取 `/etc/onlyoffice/documentserver/local.json` 中的 JWT 密钥。此时应按原生服务的实际地址修改 `REPORT_ONLYOFFICE_URL`。

ONLYOFFICE 是真实 DOCX 在线编辑功能所需的独立服务；不启动它时，报告数据管理、PDF/LIMS 导入和 Word 生成仍可使用，但在线 Word 编辑器不可用。

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
MySQL `report_generation_system`  数据库（本机服务）
data/uploads/          上传的 PDF
data/reports/          生成的 Word 文件
templates/             报告模板
mapping/               模板字段映射
```

备份时停止服务，然后复制整个 `data`、`templates` 和 `mapping` 目录。建议每天定时备份到另一块磁盘或 NAS，并设置备份保留周期。

## 生产部署

当前使用本机 MySQL，systemd 服务保持单个 Uvicorn 进程运行。对外部署建议再通过 Nginx 提供 HTTPS；文件目录应放在定期备份的独立数据盘。
