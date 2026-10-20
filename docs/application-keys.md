# 应用密钥

应用管理 → 应用市场之后的“应用密钥”独立管理数据库用户名与密码，不与资产管理中的 SSH 账号共用数据。

- 名称必填且唯一；新增必须填写密码，编辑时密码留空保留原值。密码首尾空格会保留。
- Redis 可以使用用户名为空的密钥；其他数据库需要用户名；SQLite 不使用应用密钥。
- 数据库连接选择“应用密钥”后只保存关联，每次建立物理连接读取最新凭据；更新密钥不会强制断开已有连接。
- 已关联连接的密钥不能删除，先切换连接的认证方式或更换密钥。
- 连接复制保留关联。连接配置导出不包含密码或本地密钥 ID，导入后需要重新选择密钥。

管理员可直接使用。普通角色在角色管理中授权“应用密钥”页面及查看、新增、编辑、删除、使用操作；选择密钥需要使用权限。已绑定连接的日常操作沿用数据库权限。

后端更新后运行 `python manage.py migrate database_management` 并重启 API 与数据库传输 worker。迁移 `0007_applicationkey_databaseasset_application_key` 仅新增密钥表与可空关联字段，保留已有连接、SSH 账号及凭据。

验证命令：

```text
cd backend
python manage.py test database_management accounts host_management.test_credentials --noinput
python manage.py makemigrations --check --dry-run

cd ../frontend
npm run test:run -- src/features/database-management/__tests__ src/components/tools/__tests__/ApplicationKeyManager.test.ts src/components/tools/__tests__/AccountManager.behavior.test.ts src/components/tools/__tests__/AccountManager.elementPlus.structure.test.ts
npm run build
```
