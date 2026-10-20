# 统一 SSH 账号与数据库连接清理

账号管理统一保存 SSH 凭据，不再区分账号类型。迁移
`host_management.0014_remove_hostcredential_credential_type` 仅删除类型字段，
保留账号、用户名、密码、私钥和备注。SSH 候选包含全部账号，缺少用户名的记录仍跳过。

旧客户端传入的 `credentialType` 会被忽略，响应暂固定返回 `host`。
新备份不输出类型，旧备份导入时忽略类型。数据库连接独立填写凭据，
不再读取账号管理；独立 SSH 跳板机和 SSL 配置继续保留。

## 当前环境清理命令

在 `backend/` 使用当前环境配置执行，默认只预览数量：

```powershell
python manage.py clear_database_connections
```

显式删除当前环境所有数据库连接资产和已保存查询：

```powershell
python manage.py clear_database_connections --execute
```

执行会先取消关联的未完成任务（包括连接清单导入任务）。如仍有运行任务，
命令保留连接并报错；待 worker 完成取消后重新执行。已提交的任务批次不会回滚。

清理保留资产目录、账号、历史任务及其输入和结果文件，不连接或删除远端数据库。
命令可重复执行；清理不在自动迁移中运行。数据库页面刷新连接列表时，会移除
失效的选中项、工作区标签及固定对象缓存。
