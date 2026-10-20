# MySQL 连接设置

MySQL 新建与编辑共用 `MysqlConnectionDialog.vue`，提供常规、高级、参数、SSL 四页。其他数据库继续使用原表单。测试连接只提交当前草稿，不创建或更新资产；保存不依赖测试成功。

## 配置和凭据

- 非敏感配置存放于资产 `options`，参数只接受读取超时、写入超时、自动提交、SQL 模式和会话时区。
- 数据库密码继续使用原加密字段。编辑留空保留，选择“无密码”明确清空。
- SSH 与 TLS 材料使用迁移 `0006_connection_secrets` 增加的加密字段。`connectionSecrets` 只写，省略保留、`null` 移除；响应仅返回文件名和已设置状态。单文件上限 256KB。
- 客户端证书和私钥由后端解析并校验配对。TLS 验证模式要求 CA，Verify Identity 验证真实 MySQL 主机名，包括经 SSH 转发的情况。启用 SSL 后拒绝不支持 TLS 的服务端，避免明文降级。
- 连接、SSH 转发及 TLS 临时文件按请求或任务释放。连接复制保留加密配置，连接配置导出不包含凭据正文；导入预检提示补全材料。

## 只读与到期

所有 MySQL 连接入口使用统一连接器。只读连接允许读取和导出，拒绝写入、DDL、导入和账号修改，同时设置 MySQL 只读事务。用户 SQL 限制为单条读取语句，拒绝过程调用、多语句、文件读写和修改会话的语句；导出内部使用独立的只读快照初始化。

连接到期后禁止新操作，后台任务在开始及批次边界复核当前设置。策略失败立即停止任务，即使启用错误时继续；已提交批次保留。仍可编辑、删除连接资产和下载已生成结果。

## 验证记录

- `npm run test:run -- src/features/database-management`：12 个文件、77 项通过。
- `python manage.py test database_management --noinput`：101 项通过。
- `npm run build`：通过，保留既有的大包体提示。
- `python manage.py makemigrations --check --dry-run`：无遗漏迁移。
- 本地已应用 `0006_connection_secrets`；其他运行环境需正常执行 `python manage.py migrate`。
- 浏览器用实际组件和项目全局样式进行无数据库连接的预览检查，覆盖 1920、1280、768、390px、浅色、深色和自定义紫色。截图保存在本地 `.codex-logs/mysql-connection/`。会话失效后的截图使用临时预览页，未修改已有连接。
- SSH/TLS 清理和真实证书解析、配对及主机名模式已有自动化覆盖；真实远端 SSH + MySQL TLS 联通仍需可用目标环境验证。

本地预览截图（未纳入版本控制）：[桌面常规页](../.codex-logs/mysql-connection/desktop-1920-light-general.png)、[深色 SSL 页](../.codex-logs/mysql-connection/tablet-768-dark-ssl.png)、[移动端紫色主题](../.codex-logs/mysql-connection/mobile-390-purple-general.png)。
