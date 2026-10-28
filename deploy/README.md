# 部署

沿用 fileHub 的部署模式：前后端独立镜像、显式配置文件和独立数据目录。Django 静态资源在构建 frontend 镜像时收集并打包进 Nginx 镜像；Kubernetes 拆分 app/web Deployment。以下命令在仓库根目录执行，要求 Docker Compose v2；Windows 请在 WSL/Linux 容器环境运行。

## 目录

```text
deploy/
├── app.conf.example          # Django 配置样例
├── redis.conf.example        # API/Worker 共用 Redis 配置样例
├── backend.Dockerfile        # API 和 Worker 共用镜像
├── backend-entrypoint.sh     # 校验配置、迁移、收集静态文件和启动
├── frontend.Dockerfile       # Vue 和 Django 静态文件构建 + Nginx
├── nginx.conf                # Compose 的代理配置
├── docker-compose.yaml       # 使用已构建的镜像启动
└── k8s/                      # app/web、Redis、Service 和可选 Ingress
```

本机 `app.conf`、`redis.conf` 和 `data/` 已被 Git/Docker 构建上下文忽略。不要把真实凭据填写到样例中。

## Docker Compose

复制配置：

```bash
cp deploy/app.conf.example deploy/app.conf
cp deploy/redis.conf.example deploy/redis.conf
python -c 'import secrets; print(secrets.token_urlsafe(64))'
```

将生成的值填入 `deploy/app.conf` 的 `DJANGO_SECRET_KEY`，该密钥必须保持稳定并备份。配置仍使用项目原生的 `KEY=VALUE` 格式，不使用 fileHub 的 YAML 配置解析器。

### 常用 Django 配置

配置已集中在 `app.conf.example`，按用途分组。普通配置的优先级为配置文件、环境变量、代码默认值；布尔值用 `0/1`，列表用逗号分隔。Redis 文件路径在容器中由 `REDIS_CONFIG_FILE` 环境变量优先指定。

| 场景 | 对应配置 |
| --- | --- |
| 域名变更、400/CSRF 来源错误 | `DJANGO_ALLOWED_HOSTS`、`DJANGO_CSRF_TRUSTED_ORIGINS` |
| HTTPS 代理识别、重定向循环 | `DJANGO_TRUST_PROXY_SSL_HEADER`、`DJANGO_SECURE_SSL_REDIRECT` |
| 跨域登录、Cookie 丢失 | `DJANGO_CORS_ALLOWED_ORIGINS`、`DJANGO_CORS_ALLOW_CREDENTIALS`、Session/CSRF Cookie 的 Secure、SameSite 和 Domain |
| 会话有效期 | `DJANGO_SESSION_COOKIE_AGE`（秒）、`DJANGO_SESSION_EXPIRE_AT_BROWSER_CLOSE` |
| 上传数据过大、字段/文件过多 | `DATA_UPLOAD_MAX_MEMORY_SIZE`、`DATA_UPLOAD_MAX_NUMBER_FIELDS`、`DATA_UPLOAD_MAX_NUMBER_FILES` |
| 上传占用内存、临时目录 | `FILE_UPLOAD_MAX_MEMORY_SIZE`、`FILE_UPLOAD_TEMP_DIR` |
| 数据库锁等待、连接超时 | `DATABASE_SQLITE_TIMEOUT`、`DATABASE_CONNECT_TIMEOUT`（秒） |
| 静态资源、媒体及任务文件路径 | `DJANGO_STATIC_*`、`DJANGO_MEDIA_*`、`DATABASE_TRANSFER_DIR` |
| 语言、时区 | `DJANGO_LANGUAGE_CODE`、`TZ`、`DJANGO_USE_TZ` |

可信 HTTPS 代理后可启用 `DJANGO_TRUST_PROXY_SSL_HEADER=1` 和 Session/CSRF Secure Cookie；仅在代理覆盖该请求头时信任它。HSTS 默认关闭，确认 HTTPS 正常后再配置。ASGI 默认保持 `DATABASE_CONN_MAX_AGE=0`。上传文件内存阈值表示何时写入临时文件，并非上传文件总大小上限；数据库导入大小通过 `DATABASE_TRANSFER_MAX_UPLOAD_BYTES` 控制，也要同步入口代理的限制。静态或媒体 URL 修改时同步 Nginx 路由。

`DATABASE_TRANSFER_DIR` 已配置到 API/Worker 共用的 `/data/database-transfer`。已有私有配置需要补上该键。Kubernetes 的 Secret 样例包含同一组配置，按其环境保留网关和站点差异。

- 域名/IP：修改 `DJANGO_ALLOWED_HOSTS`，多个值逗号分隔；修改 `DJANGO_CSRF_TRUSTED_ORIGINS` 为实际完整来源，例如 `https://ops.example.com`。
- 数据库：默认 SQLite `/data/db.sqlite3`；MySQL 设 `DATABASE_ENGINE=mysql` 并填写 `DATABASE_*`，MySQL 为外部服务。
- Redis：默认 `redis://redis:6379/3`，API 与 Worker 挂载同一个 `redis.conf`。
- RDP：Compose 使用 `GUACD_HOST=guacd`。

构建并启动，与 fileHub 一样，Compose 只负责运行镜像：

```bash
docker build -f deploy/backend.Dockerfile -t devops-tools-backend:latest .
docker build -f deploy/frontend.Dockerfile -t devops-tools-frontend:latest .
docker compose -f deploy/docker-compose.yaml up -d
docker compose -f deploy/docker-compose.yaml ps
curl -f http://localhost:8088/api/health/
```

入口为 `http://localhost:8088`，需要更换端口时修改 frontend 的 `ports`。frontend 镜像构建时运行 Django `collectstatic`，并将产物放入 Nginx 镜像的 `/srv/devops-static`，由 Nginx 提供 `/static/`。backend 启动时也会收集静态文件供 WhiteNoise 使用，然后运行 Daphne。更新后端 Admin 或其他 Django 静态资源时，需重新构建并部署 frontend 镜像。Worker 等待 backend 健康后启动，不重复执行迁移。Redis 开启 AOF；Redis 和 guacd 不对宿主机暴露端口。

| 宿主机目录 | 容器路径 | 内容 |
| --- | --- | --- |
| `deploy/data/devops_data/` | `/data` | SQLite、媒体、录像、数据库资产文件 |
| `deploy/data/redis/` | Redis `/data` | AOF 和持久化数据 |

创建管理员、检查日志和停止服务：

```bash
docker compose -f deploy/docker-compose.yaml exec backend python manage.py createsuperuser
docker compose -f deploy/docker-compose.yaml logs --tail=100 backend transfer-worker frontend
docker compose -f deploy/docker-compose.yaml down
```

配置修改后用 `docker compose -f deploy/docker-compose.yaml restart backend transfer-worker` 重启。Nginx 代理 API、admin、媒体和 WebSocket，提供静态文件；允许大文件上传。生产环境在可信入口设置 HTTPS，并正确传递 Host、WebSocket Upgrade 和 `X-Forwarded-Proto`。

## 发布镜像

与 fileHub 使用相同的发布脚本参数，镜像名为 `devops-tools-backend`、`devops-tools-frontend`，默认仓库 `registry.cn-beijing.aliyuncs.com/kaikai136`：

```bash
docker login registry.cn-beijing.aliyuncs.com
sh publish-images.sh v1.0.0 --dry-run
sh publish-images.sh v1.0.0 --keep-images
```

默认发布后删除本地对应标签，`--keep-images` 保留。使用发布镜像部署 Compose 时，把两个服务和 Worker 的 `image` 改成相同版本的完整仓库地址，再执行 `pull` 和 `up -d`。

## Kubernetes

采用 fileHub 的独立 app/web Deployment 与 hostPath 挂载方式。app Pod 包含 API、Worker 和 guacd；web 独立运行 Nginx，通过 Service 访问 API；Redis 独立 Deployment，开启 AOF。

部署前修改：

1. `deployment-app.yaml`、`deployment-web.yaml` 的 `REPLACE_WITH_NODE_NAME` 必须填写同一个节点的 `kubernetes.io/hostname` 标签值，以共享静态文件。`redis.yaml` 的 `REPLACE_WITH_REDIS_NODE_NAME` 单独指定 Redis 固定节点，可以与 app/web 不同。Redis 通过 ClusterIP Service 访问，应用连接地址不需要改为节点 IP。hostPath 数据属于指定节点，切换节点前必须迁移数据。
2. 所有前后端镜像改成已发布的固定版本。应用保持单副本和 Recreate，避免 SQLite 多实例写入。
3. 复制 `app-config.secret.example` 为 `app-config.local.yaml`，按环境修改域名和数据库配置。样例内置仅用于首次启动的演示密钥，生产环境必须替换为稳定的随机密钥；已有加密凭据时必须沿用原密钥。Kubernetes 使用 `GUACD_HOST=127.0.0.1`。私有文件已忽略，不提交。

```bash
cp deploy/k8s/app-config.secret.example deploy/k8s/app-config.local.yaml
# 编辑上述配置与 Deployment 后执行
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/app-config.local.yaml
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/redis.yaml
kubectl apply -f deploy/k8s/deployment-app.yaml
kubectl apply -f deploy/k8s/deployment-web.yaml
kubectl -n middleware rollout status deployment/devops-tools-app
kubectl -n middleware rollout status deployment/devops-tools-web
kubectl -n middleware port-forward service/devops-tools-web 8088:80
```

数据目录为节点上的 `/data/middleware/devops-tools/{data,static,redis}`。Service 默认 ClusterIP。需要外部 HTTPS 时，修改 `04-project-ingress.yaml` 的域名、IngressClass 和 TLS Secret，再单独 apply；模板不依赖特定的 cert-manager Issuer，证书 Secret 需预先提供。更新 Secret/ConfigMap 后重启 app/web Deployment。

使用 HTTP NodePort 访问时，`DJANGO_SESSION_COOKIE_SECURE` 和 `DJANGO_CSRF_COOKIE_SECURE` 必须保持 `0`（模板默认值）；仅在使用 HTTPS 访问时改成 `1`。否则浏览器无法回传 Session Cookie，滑块挑战即使刚生成也会提示“滑块验证已过期”。修改已有部署的私有 Secret 配置后，重新 apply 并执行 `kubectl -n middleware rollout restart deployment/devops-tools-app`，待启动完成后清除站点 Cookie 并刷新页面重试。`DJANGO_CSRF_TRUSTED_ORIGINS` 也应填写实际来源（包含协议和非默认端口）。

## 备份与升级

停止 API、Worker 和 Redis 后备份运行配置及全部数据目录；外部 MySQL 单独备份。更新镜像后重新启动，backend 会执行迁移。回滚代码不会回滚数据库，恢复时需要匹配的数据库、文件和配置备份。

本次重建不自动迁移旧部署数据。若已有数据，先停止旧实例，将旧数据库复制到新的 `/data/db.sqlite3` 对应宿主机路径，媒体、录像及资产文件按配置迁移；将原密钥写入新 `DJANGO_SECRET_KEY`。核对后再启动，避免使用新密钥解密旧数据。
