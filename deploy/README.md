# 部署

采用 fileHub 的双镜像模式：Django/Daphne 后端 + Nginx/Vue 前端。Redis、guacd和数据库传输 worker 按本项目功能保留。

## Docker Compose

在仓库根目录运行 `bash deploy/scripts/compose-up.sh`。入口为 `http://localhost:8088`。

启动前检查 `deploy/config/app.conf`：生产环境设置允许的域名和 CSRF 来源。SQLite 默认为 `/data/data/db.sqlite3`，需要 MySQL 时填写外部数据库连接配置。真实配置不要提交到 Git。

运行数据全部保存在 `deploy/data/`。旧部署数据不会自动搬迁：先停止旧服务并备份，再根据旧挂载目录把数据库、密钥、媒体和录像复制到对应的新目录。不要对已有数据运行 `down -v`。

手动构建启动：`docker compose -f deploy/docker-compose.yml up -d --build`。停止：`docker compose -f deploy/docker-compose.yml down`。

发布镜像：`bash publish-images.sh latest`；可使用 `--dry-run`。

## Kubernetes

先发布镜像，修改 `deploy/k8s/kustomization.yaml` 中镜像地址/标签；按集群设置 PVC 的 storageClass。当前 SQLite 模式只能运行一个 backend 副本。前后端通过同一 Pod 的 localhost 通信，静态文件用共享卷，运行数据使用 PVC。

执行 `kubectl apply -k deploy/k8s`。默认 Service 为 ClusterIP，请自行配置 Ingress、LoadBalancer 或 port-forward。Redis 默认仅用于内部部署；生产环境按需要更换为外部 Redis。

验证：`bash deploy/scripts/tests/test-deployment.sh`。
