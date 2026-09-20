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
- 静态资源：前端构建后由 Django + WhiteNoise 提供。
- 数据存储：支持远程 MySQL 或 SQLite，上传文件和密钥通过挂载目录持久化。
- 部署方式：Docker 多阶段构建，Docker Compose 编排 app 与 guacd 服务，数据库由运行时 `data/config/app.conf` 指定。

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
    ├── config/app.conf      # 运行时 data/config/app.conf 的默认模板
    ├── docker/              # 容器启动脚本
    ├── k8s/                 # Kubernetes 部署清单
    ├── scripts/             # 本地/远程部署脚本
    ├── Dockerfile           # 前后端多阶段构建镜像
    └── docker-compose.yml   # app + guacd 基础服务编排
```

## 本地开发

### 本地配置文件


常用本地启动项：

```conf
```

本地配置只放安全默认值。生产和 Docker Compose 部署不要改这个文件，部署环境继续使用 `data/config/app.conf`。

### 后端手动启动

批量执行使用现有 SSH/SFTP 传输层，不再要求额外的自动化执行引擎。后端开发仍建议使用 Linux 或 WSL，以保持与部署环境一致。

首次准备依赖：

```powershell
wsl.exe --cd /mnt/c/Users/kaikai/Desktop/django-vue/backend -e /root/venv-opstool/bin/python -m pip install -r requirements.txt
```

执行迁移：

```powershell
wsl.exe --cd /mnt/c/Users/kaikai/Desktop/django-vue/backend -e env APP_CONFIG_FILE=/mnt/c/Users/kaikai/Desktop/django-vue/config/local.app.conf /root/venv-opstool/bin/python manage.py migrate
```

启动后端：

```powershell
cd backend
.\start-wsl.ps1
```

`backend/start-wsl.ps1` 会读取 `config/local.app.conf`，设置 `APP_CONFIG_FILE`，并按 `BACKEND_HOST`、`BACKEND_PORT` 启动 Daphne。

后端默认地址：

```text
http://127.0.0.1:8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/api/health/
```

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

### 前端生产构建

```powershell
cd frontend
npm run build
```

## Docker 部署

### 镜像构建与运行时配置

构建镜像时不会读取 `config/local.app.conf`，也不会把真实生产配置写入镜像。镜像只包含应用代码、Python 依赖和前端构建产物；容器启动后由入口脚本读取 `/app/config/app.conf`。

单独构建镜像：

```bash
docker build -f deploy/Dockerfile -t devops-tools:latest .
```

或使用脚本指定镜像名：

```bash
bash deploy/scripts/build-image.sh devops-tools:latest
```

修改密码

```
docker exec -it devops-tools python manage.py changepassword admin
```



### 拉取后配置并启动

仓库已提供不含真实密钥的默认 `deploy/config/app.conf` 模板。启动脚本会在首次运行时复制到 `data/config/app.conf`，Compose 会把外部 `data` 目录挂载到容器内 `/app`，应用直接从 `/app/config/app.conf` 读取部署配置：

```bash
git clone https://github.com/kaikai136/devops-tools.git
cd devops-tools
vim data/config/app.conf
bash deploy/scripts/compose-up.sh
```


如果手动执行 Docker Compose，MySQL 和 SQLite 模式都使用同一个基础 Compose 文件：

```bash
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps
```


部署完成后访问：

```text
http://服务器IP:8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/api/health/
```

预期返回：

```json
{"status":"ok"}
```

### 默认配置文件

`deploy/config/app.conf` 会提交到仓库，用于本地、测试和受控内网环境的开箱即用部署。它只包含公开默认值，不包含真实生产密钥：

```conf
TZ=Asia/Shanghai
DJANGO_SECRET_KEY=
DJANGO_SECRET_KEY_FILE=/app/data/django-secret-key
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=*
DJANGO_CSRF_TRUSTED_ORIGINS=
DJANGO_CORS_ALLOW_ALL_ORIGINS=0
DJANGO_MEDIA_ROOT=/app/media
DJANGO_SERVE_MEDIA_FILES=1

DATABASE_ENGINE=mysql
DATABASE_HOST=mysql.example.com
DATABASE_PORT=3306
DATABASE_NAME=devops_tools
DATABASE_USER=devops_tools
DATABASE_PASSWORD=devops-tools-password


DJANGO_DB_PATH=/app/data/db.sqlite3

GUACD_HOST=guacd
GUACD_PORT=4822
RDP_RECORDING_ROOT=/app/recordings
RDP_RECORDING_RETENTION_DAYS=30
RDP_RECORDING_DEFAULT_ENABLED=0

SSH_GATEWAY_ENABLED=1
SSH_GATEWAY_BIND_HOST=0.0.0.0
SSH_GATEWAY_PORT=2222
SSH_GATEWAY_PUBLIC_HOST=
SSH_GATEWAY_PUBLIC_PORT=2222
SSH_GATEWAY_HOST_KEY_PATH=/app/data/ssh-gateway-host-key
```

其中 `DJANGO_ALLOWED_HOSTS=*` 只是为了让新部署能够直接访问。**生产环境必须改为实际域名或服务器 IP**，并正确配置 `DJANGO_CSRF_TRUSTED_ORIGINS`。

### Django 密钥自动生成

默认 `data/config/app.conf` 中的 `DJANGO_SECRET_KEY` 为空。容器每次启动时按以下优先级确定密钥：

1. 使用 `data/config/app.conf` 中非空的 `DJANGO_SECRET_KEY`。
2. 读取已经存在的 `/app/data/django-secret-key`。
3. 首次启动时安全生成新密钥并保存到 `/app/data/django-secret-key`。

由于 `deploy/docker-compose.yml` 将外部 `data` 目录挂载到容器 `/app`，自动生成的密钥在宿主机上的位置是：

```text
./data/django-secret-key
```

重新启动容器、重新构建镜像或执行 `docker compose -f deploy/docker-compose.yml up -d --force-recreate` 都会继续使用同一密钥。密钥内容不会输出到日志。

> 删除 `./data` 会删除自动生成的 Django 密钥和其他本地数据文件。删除、迁移或重装前必须备份 `data`、`media`；如果使用远程 MySQL，还需要按远程数据库的备份策略单独备份数据库。

### 生产环境私有配置

可以直接编辑远端服务器上的 `data/config/app.conf`。远程部署脚本会在 Git 更新前临时备份这个文件，并在更新后恢复，避免仓库默认模板覆盖私有配置。

如果需要在本地保留一份私有模板，可以复制为 Git 忽略的本地文件：

```bash
cp deploy/config/app.conf data/config/app.conf
```

示例：

```conf
DJANGO_SECRET_KEY=请替换为强随机密钥
DJANGO_ALLOWED_HOSTS=ops.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://ops.example.com
DJANGO_CORS_ALLOW_ALL_ORIGINS=0
DATABASE_ENGINE=mysql
DATABASE_HOST=mysql.example.com
DATABASE_PORT=3306
DATABASE_NAME=devops_tools
DATABASE_USER=devops_tools
DATABASE_PASSWORD=请替换为强随机数据库密码
SSH_GATEWAY_PUBLIC_HOST=ops.example.com
```

如果通过反向代理使用 HTTPS，`DJANGO_CSRF_TRUSTED_ORIGINS` 必须填写带协议的外部访问来源，例如 `https://ops.example.com`。多个主机或来源使用英文逗号分隔。

### 配置项说明

| 配置项 | 默认值 | 说明与生产建议 |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | 空 | 非空时优先使用；为空时自动读取或生成持久化密钥。不要将真实生产密钥提交到仓库。 |
| `DJANGO_SECRET_KEY_FILE` | `/app/data/django-secret-key` | 容器内自动密钥文件，通常无需修改。 |
| `DJANGO_ALLOWED_HOSTS` | `*` | 允许访问的域名/IP。默认值仅为开箱即用，生产环境必须收紧。 |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | 空 | 跨站请求信任来源，必须包含 `http://` 或 `https://` 协议。使用域名、HTTPS 或反向代理时应明确设置。 |
| `DJANGO_CORS_ALLOW_ALL_ORIGINS` | `0` | 是否允许所有跨域来源。生产环境保持关闭。 |
| `DATABASE_ENGINE` | `mysql` | 数据库类型。`mysql` 连接远程 MySQL；`sqlite` 使用本地 SQLite 文件。 |
| `DATABASE_HOST` | `mysql.example.com` | 远程 MySQL 服务地址，生产环境必须改为真实主机名或 IP。 |
| `DATABASE_PORT` | `3306` | 远程 MySQL 服务端口。 |
| `DATABASE_NAME` | `devops_tools` | 远程 MySQL 数据库名称。 |
| `DATABASE_USER` | `devops_tools` | 远程 MySQL 应用用户。 |
| `DATABASE_PASSWORD` | `devops-tools-password` | 远程 MySQL 应用用户密码，生产环境必须修改。 |
| `DJANGO_DB_PATH` | `/app/data/db.sqlite3` | SQLite 数据库路径，仅 `DATABASE_ENGINE=sqlite` 时使用。 |
| `DJANGO_MEDIA_ROOT` | `/app/media` | 容器内上传文件目录。 |
| `GUACD_HOST` | `guacd` | guacd 服务地址。Compose 内默认使用服务名。 |
| `GUACD_PORT` | `4822` | guacd 服务端口。 |
| `RDP_RECORDING_RETENTION_DAYS` | `30` | RDP 录像保留天数的升级前默认值；保存系统设置“日志保留”后以系统设置为准。 |
| `RDP_RECORDING_DEFAULT_ENABLED` | `0` | 新建连接时是否默认开启 RDP 录像；仅在系统设置“日志保留”和旧 `rdp_recording` 设置都不存在时兜底。 |
| `SSH_GATEWAY_PUBLIC_HOST` | 空 | 外部 SSH/SFTP/SCP 示例命令展示的网关地址。 |
| `SSH_GATEWAY_PUBLIC_PORT` | `2222` | 外部 SSH 网关端口。 |

Compose 层的镜像名、容器名和宿主机端口已固定在 `deploy/docker-compose.yml` 中；如需改变端口映射或镜像标签，请直接修改该 Compose 文件，或用 `bash deploy/scripts/build-image.sh <image:tag>` 单独构建镜像。

### 数据持久化与备份

Docker Compose 会用一个外部目录挂载全部运行时文件：

- `../data:/app`：外部运行时根目录，容器读取 `/app/config/app.conf`，并使用 `/app/data`、`/app/media`、`/app/recordings`。

目录结构如下，其中 `config/app.conf` 需要手动确认或编辑，其他目录启动时自动创建：

```text
data/
├── config/
│   └── app.conf
├── data/
├── media/
└── recordings/
```

升级或重建镜像不会删除这些本地挂载数据。重大升级前建议同时备份：

```bash
cp data/config/app.conf data/config/app.conf.backup
cp -a data data.backup
```

如果使用远程 MySQL，请在数据库服务器或托管数据库平台上单独执行备份。

`data/`、`deploy/config/*.local.conf`、`.env`、`.env.*` 等私有文件默认被 Git 忽略，不要强制提交。

## Kubernetes 部署


部署前先编辑 `deploy/k8s/configmap.yaml` 里的 `app.conf`：

- 使用远程 MySQL：保留 `DATABASE_ENGINE=mysql`，修改 `DATABASE_HOST`、`DATABASE_PORT`、`DATABASE_NAME`、`DATABASE_USER`、`DATABASE_PASSWORD`。
- 使用 SQLite：改为 `DATABASE_ENGINE=sqlite`，并确认 `DJANGO_DB_PATH=/app/data/db.sqlite3`。
- 通过 NodePort 暴露时，默认 Web 端口是 `30271`，SSH 网关端口是 `30222`；如需调整，同时修改 `deploy/k8s/service.yaml` 和 `SSH_GATEWAY_PUBLIC_PORT`。

应用清单：

```bash
kubectl apply -k deploy/k8s
```

访问入口：

```text
Web: http://节点IP:30271
SSH: ssh <平台用户>@节点IP -p 30222
```

`devops-tools-runtime-pvc` 会挂载到容器 `/app`，其中包含 `config/app.conf`、`data/`、`media/` 和 `recordings/`，默认使用 `ReadWriteMany`。如果你的集群存储类不支持 RWX，需要改用支持共享挂载的存储，或根据集群拓扑调整 Pod 调度与 PVC 策略。


### 手动远程部署

```bash
cd /opt
git clone https://github.com/kaikai136/devops-tools.git devops-tools
cd /opt/devops-tools
bash deploy/scripts/compose-up.sh
curl http://127.0.0.1:8001/api/health/
```

部署指定标签时：

```bash
cd /opt/devops-tools
git fetch --tags --force origin
git checkout --detach refs/tags/v2.0.0
bash deploy/scripts/compose-up.sh
```

### 已有部署升级

升级前保留已有私有配置和持久化数据：

```bash
cd /opt/devops-tools
cp data/config/app.conf data/config/app.conf.backup
cp -a data data.backup
git pull --ff-only origin main
bash deploy/scripts/compose-up.sh
```

如果手工执行 Git 操作时担心运行时配置受影响，请先备份 `data/config/app.conf`。使用 `deploy/scripts/deploy-remote.sh` 时脚本会自动完成该保护流程。

### 部署验证

```bash
cd /opt/devops-tools
git describe --tags --always --dirty
git rev-parse HEAD
docker compose -f deploy/docker-compose.yml ps
curl http://127.0.0.1:8001/api/health/
```
## 常用运维命令

以下命令对远程 MySQL 和 SQLite 模式都适用，数据库选择由 `data/config/app.conf` 控制。

查看服务状态：

```bash
docker compose -f deploy/docker-compose.yml ps
```

查看应用日志：

```bash
docker compose -f deploy/docker-compose.yml logs -f app
```

查看 guacd 日志：

```bash
docker compose -f deploy/docker-compose.yml logs -f guacd
```

重启服务：

```bash
docker compose -f deploy/docker-compose.yml restart
```

重建并滚动启动：

```bash
bash deploy/scripts/compose-up.sh
```

执行数据库迁移：

```bash
docker compose -f deploy/docker-compose.yml exec app python manage.py migrate
```

按“系统设置 / 日志保留”统一清理过期日志和 RDP 录像：

```bash
docker compose -f deploy/docker-compose.yml exec app python manage.py cleanup_logs --dry-run
docker compose -f deploy/docker-compose.yml exec app python manage.py cleanup_logs
```

旧入口 `cleanup_rdp_recordings` 仍保留用于兼容既有脚本。

进入 Django shell：

```bash
docker compose -f deploy/docker-compose.yml exec app python manage.py shell
```

## 默认访问入口

- Web 应用：`http://服务器IP:8001`
- 管理后台：`http://服务器IP:8001/admin/`
- 健康检查：`http://服务器IP:8001/api/health/`
- 终端页面：`http://服务器IP:8001/terminal.html`

## 注意事项

- 生产环境必须设置强随机 `DJANGO_SECRET_KEY`。
- 如果使用远程 MySQL，生产环境必须修改 `DATABASE_HOST`、`DATABASE_USER` 和 `DATABASE_PASSWORD`，确保它们指向可访问的远程数据库。
- `DJANGO_ALLOWED_HOSTS` 和 `DJANGO_CSRF_TRUSTED_ORIGINS` 需要按实际域名/IP/端口配置。
- Web RDP 功能依赖 `guacamole/guacd:1.5.5` 容器，请确认 guacd 服务正常启动。
- SSH 终端依赖目标主机网络可达，并需要正确的登录账号、密码或密钥配置。
- 升级前建议备份整个 `data/` 目录；如果使用远程 MySQL，还要单独备份远程数据库。
