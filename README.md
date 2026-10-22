# 运维工具平台

这是一个基于 Django REST API + Vue 3 + Vite 重构的 Web 运维工具平台，提供主机资产管理、Web 终端、网络探测、安全工具、审计日志和系统管理能力。项目支持本地开发运行，也支持通过 Docker Compose 一键构建部署。

## 功能概览

### 仪表盘

- 系统总览、资产统计、用户与安全状态概览。
- 网络与主机数据聚合展示。
- 图表化展示关键指标，便于快速了解平台运行情况。

### 主机与终端管理

- 主机资产管理：维护主机名称、IP、端口、系统类型、登录账号、分组和备注信息。
- 主机分组：支持默认分组、自定义分组和分组视图。
- 主机验证：可对主机连通性、登录信息和系统信息进行探测验证。
- 批量导入导出：支持主机清单备份、导入、导出和字段选择。
- Web SSH 终端：通过浏览器连接 Linux/Unix 主机，支持终端字号、搜索、复制、快捷命令等常用操作。
- Web RDP 终端：通过 guacd 支持 Windows/RDP 连接。
- 远程文件工具：支持浏览远程目录、创建文件/目录、上传、下载、重命名、删除、权限调整等操作。
- 资源监控：在终端侧查看远程主机基础资源信息。
- 多主机执行：面向已选主机执行批量命令。
- 会话审计：记录 SSH/RDP 会话、命令风险等级、操作时间和来源。
- 操作录像：支持终端会话录像回放，RDP 录像文件可按保留周期清理。

### 网络工具

- IP 探活：对局域网 1-254 地址段进行在线探测。
- Ping 探测：检测目标主机连通性、延迟和结果趋势。
- 端口扫描：扫描常用端口或指定端口，识别开放服务。
- 机器探测：组合 Ping、端口和基础网络信息，快速判断主机可达性。
- IPv4 子网划分：支持 CIDR 计算、子网拆分、地址范围和可用主机数计算。

### 安全工具

- 双因子认证：管理 TOTP 动态口令条目，支持二维码识别、导入和导出。
- 密码生成器：生成强密码，支持长度、字符类型和强度配置。
- 密码记录：保存密码条目，支持导入、导出和历史管理。
- 登录保护：支持用户双因子登录、会话锁定和个人安全设置。

### 系统管理

- 用户管理：创建、禁用、删除用户，重置密码和重置双因子认证。
- 角色管理：配置角色权限与授权范围，控制页面和操作级权限。
- 账号管理：管理平台账号状态、权限和基本资料。
- 登录日志：查看登录时间、来源 IP、登录状态和失败原因。
- 操作日志：记录用户在平台内的关键操作，便于审计追踪。
- 个人中心：维护头像、资料、密码和登录保护设置。
- 系统设置：配置应用名称、Logo、图标、水印、页脚、主题偏好等基础参数。
- 水印与品牌：支持工作区水印和品牌展示配置。

## 技术架构

- 后端：Django、Django REST Framework、Django Channels、Daphne。
- 前端：Vue 3、Vite、TypeScript、ECharts、xterm.js、Guacamole Common JS。
- 终端能力：SSH 连接依赖 Paramiko，RDP 连接依赖 guacamole/guacd。
- 静态资源：部署时由 Nginx 提供 Vue 页面和 Django 静态文件。
- 数据存储：支持远程 MySQL 或 SQLite，上传文件和密钥通过挂载目录持久化。
- 部署方式：采用 fileHub 的前后端双镜像模式，Docker Compose 编排 API、前端、Worker、Redis 和 guacd，运行配置为 `deploy/app.conf` 与 `deploy/redis.conf`。

## 目录结构

```text
django-vue/
├── backend/                 # Django API、WebSocket、模型和业务逻辑
│   ├── accounts/            # 登录、用户资料、权限认证、会话锁定
│   ├── authenticators/      # TOTP 动态口令管理
│   ├── host_management/     # 主机资产、分组、探测、导入导出
│   ├── network_tools/       # IP 探活、Ping、端口扫描、子网计算
│   ├── operations/          # API 路由聚合和健康检查
│   ├── passwords/           # 密码生成与密码记录
│   ├── system_management/   # 系统设置、日志、仪表盘
│   ├── web_terminal/        # Web SSH/RDP 终端、文件工具、会话审计
│   └── ops_tool/            # Django 项目配置、ASGI/WSGI、前端入口
├── frontend/                # Vue 3 前端应用
│   ├── src/components/      # 页面与通用组件
│   ├── src/composables/     # 页面状态和功能逻辑
│   ├── src/services/        # API 请求封装
│   └── src/styles/          # 全局样式和功能模块样式
└── deploy/                  # Docker Compose、Dockerfile、启动脚本和 K8s 部署文件
    ├── app.conf.example     # 应用配置样例
    ├── redis.conf.example   # Redis 配置样例
    ├── data/                # 数据和静态文件（Git 忽略）
    ├── k8s/                 # Kubernetes 部署清单
    ├── backend.Dockerfile   # Django/Daphne 镜像
    ├── frontend.Dockerfile  # Vue 构建与 Nginx 镜像
    └── docker-compose.yaml  # 五个服务的编排入口
```

## 本地开发

### 本地配置文件


常用本地启动项：

```conf
APP_CONFIG_FILE=config/local.app.conf
REDIS_CONFIG_FILE=config/redis.app.conf
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8001
FRONTEND_HOST=0.0.0.0
FRONTEND_PORT=5115
VITE_API_TARGET=http://127.0.0.1:8001
VITE_WS_TARGET=ws://127.0.0.1:8001
```

本地配置只放安全默认值。部署使用 `deploy/app.conf` 与 `deploy/redis.conf`，详见 [部署指南](deploy/README.md)。

### 后端手动启动

批量执行使用现有 SSH/SFTP 传输层，不再要求额外的自动化执行引擎。后端开发仍建议使用 Linux 或 WSL，以保持与部署环境一致。


导入导出任务依赖 Redis，连接地址单独配置在 `config/redis.app.conf`。本地默认地址为 `redis://127.0.0.1:6379/3`；启动前请确保 Redis 已在该地址运行，或将配置文件中的 `REDIS_URL` 改为外部 Redis 地址。应用和任务 Worker 必须使用同一个 Redis 配置。

安装后端依赖并执行数据库迁移：

```bash
cd ~/Desktop/kaikai/devops-captain
cd backend
python -m pip install -r requirements.txt
export APP_CONFIG_FILE="$(realpath ../config/local.app.conf)"
python manage.py migrate
```

启动后端 API/WebSocket 服务：

```bash
cd ~/Desktop/kaikai/devops-captain/backend
export APP_CONFIG_FILE="$(realpath ../config/local.app.conf)"
python -m daphne -b 0.0.0.0 -p 8001 ops_tool.asgi:application
```

数据库导入导出由独立 Worker 异步处理。另开一个终端并使用相同配置启动：

```bash
cd ~/Desktop/kaikai/devops-captain/backend
export APP_CONFIG_FILE="$(realpath ../config/local.app.conf)"
python manage.py run_database_transfer_worker --poll-interval 1
```


后端默认地址：

```text
http://127.0.0.1:8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/api/health/
```

健康检查正常时返回 `{"status":"ok"}`。若只启动 Daphne 而未启动 Worker，普通 API 可用，但导入导出任务会停留在队列中等待处理。

MySQL/MariaDB 表及整库导入导出统一使用 UTF-8 `.sql` 转储。导出可选择当前表、勾选表或数据库全部表，以及结构和数据、仅结构或仅数据；关系库 CSV、ZIP 和 JSON 快照入口已移除，其他关系库暂不支持此转储功能。Redis、查询 SQL 文件和连接配置功能保持不变。

导入文件通过分片上传后由 Worker 预检，在顶部消息按钮中查看逐表冲突、预计行数和兼容性警告，再选择追加（默认）、覆盖或跳过并确认执行。文件只允许受支持的表结构、常量 INSERT 和安全会话设置，不执行任意 SQL；文件中的 DROP 不会直接执行。覆盖结构会删除重建表，MySQL DDL 无法保证回滚；重试会保留已完成表检查点，仍需确认。

行数、表数、上传和结果大小的 `DATABASE_TRANSFER_MAX_*` 配置默认 `0`（无固定业务上限），仍受磁盘空间、超时和内存保护约束。`DATABASE_TRANSFER_MAX_SQL_STATEMENT_BYTES` 默认 64 MiB，仅限制单条 SQL；超大 INSERT 应拆分，不限制文件总大小。历史未过期结果仍可下载，旧格式未结束任务需重新提交。

### 前端手动启动

```powershell
cd frontend
npm install
npm run dev
```

`frontend/vite.config.ts` 会读取 `config/local.app.conf`，用 `FRONTEND_HOST`、`FRONTEND_PORT` 控制本地 Vite 服务，并用 `VITE_API_TARGET`、`VITE_WS_TARGET` 代理后端 API、媒体文件和 WebSocket。

前端默认地址：

```text
http://localhost:5173
```

## Docker 部署

部署目录已按 fileHub 的独立后端/前端镜像模式重建，旧单体 Dockerfile 和旧部署脚本已移除。

完整的启动、配置、数据迁移及 Kubernetes 说明见 [deploy/README.md](deploy/README.md)。

```bash
cp deploy/app.conf.example deploy/app.conf
cp deploy/redis.conf.example deploy/redis.conf
# 按部署指南填写密钥及站点配置后构建启动
docker build -f deploy/backend.Dockerfile -t devops-tools-backend:latest .
docker build -f deploy/frontend.Dockerfile -t devops-tools-frontend:latest .
docker compose -f deploy/docker-compose.yaml up -d
```

入口为 `http://localhost:8088`。


## 注意事项

- 生产环境必须设置强随机 `DJANGO_SECRET_KEY`。
- 如果使用远程 MySQL，生产环境必须修改 `DATABASE_HOST`、`DATABASE_USER` 和 `DATABASE_PASSWORD`，确保它们指向可访问的远程数据库。
- `DJANGO_ALLOWED_HOSTS` 和 `DJANGO_CSRF_TRUSTED_ORIGINS` 需要按实际域名/IP/端口配置。
- Web RDP 功能依赖 `guacamole/guacd:1.5.5` 容器，请确认 guacd 服务正常启动。
- SSH 终端依赖目标主机网络可达，并需要正确的登录账号、密码或密钥配置。
- 升级前建议备份整个 `data/` 目录；如果使用远程 MySQL，还要单独备份远程数据库。


## Star History

<a href="https://www.star-history.com/?repos=kaikai136%2Fdevops-captain&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=kaikai136/devops-captain&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=kaikai136/devops-captain&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=kaikai136/devops-captain&type=date&legend=top-left" />
 </picture>
</a>
