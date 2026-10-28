import json
import re
from datetime import datetime
from pathlib import Path

root = Path(__file__).parent
d = json.loads((root/'2026-10-23-authenticated-results.json').read_text())
assert d.get('finished'), 'Wait for the corrected probe to finish'
e = json.loads((root/'2026-10-23-export-results.json').read_text())
duration = (datetime.fromisoformat(e['task']['finishedAt'])-datetime.fromisoformat(e['task']['startedAt'])).total_seconds()
metrics = {}
for sample in d['samples']:
    for name, cpu, mem in re.findall(r'^\S+\s+(backend|transfer-worker|frontend|redis|guacd)\s+(\d+)m\s+(\d+)Mi', sample['metrics'], re.M):
        old = metrics.setdefault(name, [0, 0]); old[0] = max(old[0], int(cpu)); old[1] = max(old[1], int(mem))
lines = ['# 2026-10-23 认证业务性能复测报告', '',
         '结论：本轮观测没有发现服务器 CPU/内存耗尽；但认证接口在 50 并发下有明显排队，CSV 后台导出吞吐异常偏低。优先优化等待与采集方式，现阶段没有证据支持先扩服务器内存。', '',
         '## 范围与方法', '',
         f'测试窗口：{d["started"]} 至 {d["finished"]}。入口为指定 NodePort，命名空间 middleware。应用管理员真实登录成功后使用该会话测试；四台既有 Linux 主机使用平台配置凭据。报告和脚本不保存密码及 Cookie。', '',
         'HTTP 使用本地 Windows requests 线程池，10/25/50 并发，每档 50/125/250 请求；每次请求新建 HTTP 连接，所有请求复用一个已登录会话。这是短突发和单会话测试，不代表 50 个独立用户，也没有覆盖登录接口高并发。首页仅测试 HTML 响应，不含浏览器 JS 执行。', '',
         '为纠正监控 GET/POST 方法和记录计时曾多次复测，早期窗口存在重叠与导出混合负载；下表仅采用最后完整窗口，此时导出已完成。稳定性期间另有少量 Channels 微基准。旧匿名结果另存 anonymous-report，不能作为严格 A/B 对照。稳定性为约五分钟轻负载，不是小时级长稳或持续高并发测试。轮询在采集后再等待约30秒。', '',
         '## HTTP 实测', '', '|路径/并发|请求数|状态计数|RPS|P50 ms|P95 ms|最大 ms|', '|---|---:|---|---:|---:|---:|---:|']
for s in d['stages'][:9]:
    lines.append(f'|{s["label"]}|{s["requests"]}|{s["codes"]}|{s["rps"]}|{s["p50_ms"]}|{s["p95_ms"]}|{s["max_ms"]}|')
lines += ['', '早期复测静态首页出现一次 ConnectionError，最后完整窗口未复现；不能据此认定服务端崩溃或忽略该失败。早期原始窗口未单独保存，只有过程观测，不能做错误率统计。当前脚本没有保留错误消息，后续应补充分层网络观测。延迟包括客户端调度、网络、建连及服务端耗时。RPS 为本次观测值，不是最大容量。', '', '## 容器资源', '',
          '以下为 Metrics API 窗口平均值的观测最大样本，不是瞬时峰值。HTTP 突发很短，可能被采样窗口平滑。CPU 1000m = 一核；各容器最大值不一定同一时刻发生。', '', '|容器|最大观测 CPU m|最大观测 MiB|', '|---|---:|---:|']
for name, values in metrics.items(): lines.append(f'|{name}|{values[0]}|{values[1]}|')
lines += ['', 'Pod 全程 Ready，backend/worker/Redis 未重启；frontend 原有一次重启，测试未新增。节点 CPU/内存样本及最终状态见 JSON。最终磁盘检查根分区约 34%，约 62G 可用。短窗口内无资源耗尽证据；无法判断小时级内存泄漏或未采样的瞬时 CPU 峰值。', '', '## 主机采集、SSH 与稳定性', '']
for s in d['stages'][9:]:
    if s['label'] == 'stability-four-host-monitor': continue
    lines.append(f'- {s["label"]}：{s["requests"]} 次，{s["codes"]}，P95 {s["p95_ms"]}ms，最大 {s["max_ms"]}ms。')
mon = [s for s in d['stages'] if s['label'] == 'stability-four-host-monitor']
lines += [f'- 稳定性阶段四主机采集 {len(mon)} 轮，共 {sum(s["requests"] for s in mon)} 次，状态：{[s["codes"] for s in mon]}。',
          '- SSH 只验证握手与终端输出，收到 banner 后关闭；没有执行高负载命令、文件传输或长期保持终端。四样本 P95 采用脚本下标分位，仅供参考，应同时看最大值。',
          '- 没有 Windows/RDP 目标，RDP、guacd 高负载和录像未覆盖；不能用 guacd 空闲内存推算 RDP 容量。仅有四台 Linux，未模拟百台真实主机。', '', '## 数据库测试', '',
          '仅新建独立 SQLite 测试资产/文件，未访问应用自身数据库。第二个测试库创建表成功，插入 10,000 行约 144ms，COUNT 验证约 85ms（API 端到端）。',
          f'第一测试库使用 exportVersion=2 的后台 CSV 任务成功，下载 {e["bytes"]} 字节，10,000 行 ID 逐行校验通过；worker 从 startedAt 到 finishedAt 为 {duration:.2f} 秒，约 {10000/duration:.1f} 行/秒。该速度明显偏慢，不能作为正常吞吐目标。',
          '旧资产 /export/ CSV 入口和 SQLite SQL dump 返回 400；当前 SQL dump/行导入限制 MySQL/MariaDB。平台没有现成数据库资产，因此未进行 MySQL 导入、导出往返、大文件导入或事务压力测试。不能声称已完成数据库导入压测。',
          '两个测试资产/SQLite 文件已删除，CSV 任务与结果文件通过任务删除 API 清理；清理后资产数为 0。测试产生的正常审计记录保留。详见 sqlite-results、export-results。', '',
          '## 解决方案与优先级', '',
          '1. 优先处理 CSV 导出同步通知等待：在 worker 内对空组连续三次 Channels group_send 分别为 3.144/3.070/3.068 秒，有成员组两次为 3.074/3.068 秒。源码每 500 行会写进度并同步推送，打包阶段也调用心跳；这是较强热点证据，但仍需给读取、写库、Channels、打包分别计时才能量化完整占比。降低推送频率、复用连接、将通知与导出解耦并设置超时；再分解 Redis 建连/命令往返、DNS 与 sync/async 桥接。不能把通知等待直接等同 Redis CPU 不够。',
          '2. 认证 API 加 Nginx request_time/upstream_response_time、应用路由和 SQL 耗时观测。用独立客户端会话、HTTP keep-alive，分别直连 Service 与 NodePort 对照，定位 50 并发排队和连接错误。当前窗口没有足够信息将延迟全部归因 SQLite。',
          '3. 主机采集按 host 缓存 5～10 秒、合并并发重复采集、限制采集 worker 并发，并在页面隐藏时暂停轮询。当前每次采集新建 SSH 且远端 sleep 1；百台每 5 秒轮询约产生 20 次新连接/秒，这是估算，不是实测容量。更大规模建议 agent/node_exporter。',
          '4. 增加写业务前评估迁移外部 MySQL，以及 Redis/cached_db Session；迁移须回归登录、验证码、注销和会话审计。当前数据库 Session 和进程内缓存不宜直接靠增加副本解决；先验证共享状态、终端路由与任务领取语义。',
          '5. 保持当前资源上限，接入持续 CPU throttling、内存、磁盘延迟、文件描述符和连接数监控。资源预算应由未来 RDP、录像和大导入实测确定，不能按当前空闲值大幅缩限。',
          '6. 下一轮使用专用测试 MySQL 和 Windows 目标，做导入导出往返、长连接/录像、30～60 分钟稳态，独立用户 10/25/50 分级。建议轻接口 P95 <500ms、错误率 <0.1%、无重启作为初步验收线；本次不足以宣称 50 用户业务达标。', '',
          '## 证据', '', '- 2026-10-23-authenticated-results.json：最终复测原始指标。', '- 2026-10-23-channel-probe*.json：worker 内 Channels 同步通知微基准；临时测试组成员已移除。',
          '- 2026-10-23-export-results.json：后台导出状态、校验和清理。', '- 2026-10-23-sqlite-results.json：隔离表操作与接口限制。', '- 2026-10-23-anonymous-report.md 和旧 load-results：此前匿名基线，范围不同。', '']
(root/'2026-10-23-report.md').write_text('\n'.join(lines), encoding='utf-8')
print(metrics)
