# Lumina

Lumina 是一个长期运行的 A 股智能监控与研究系统。当前已具备 Mock 与腾讯批量行情
采集、内存行情窗口、涨跌幅告警、SQLite 持久化和企业微信通知。生产配置默认保持
Mock，腾讯行情和企业微信都必须显式启用。

## 环境要求

- Ubuntu 22.04 LTS
- Python 3.11+
- systemd

## 本地安装

```bash
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
```

启动服务：

```bash
.venv/bin/lumina \
  --settings config/settings.yaml \
  --stocks config/stocks.yaml \
  --rules config/rules.yaml
```

按 `Ctrl+C` 后，服务会完成当前任务并安全停止。SQLite 数据默认写入
`data/lumina.db`，该目录中的运行数据不会提交到 Git。

启动时会检查三个配置文件、日志目录、数据目录和配置时区下的系统时间。
日志同时输出到控制台和 `logs/lumina.log`。
文件日志按 10 MiB 轮转并保留 10 份历史文件，不要再用外部 logrotate 操作同一文件。

行情采集配置位于 `settings.yaml`：

```yaml
market:
  source: mock
  interval_seconds: 5
  mock:
    seed: 42
  tencent:
    url: https://qt.gtimg.cn/q=
    timeout_seconds: 3
    batch_size: 50
    max_attempts: 2
    retry_backoff_seconds: 0.5
    max_total_seconds: 8
```

当前 `mock` 和 `tencent` 可运行，`sina` 仍会在启动阶段明确报错。腾讯源使用 HTTPS
批量获取沪深指数、ETF 和个股，网络请求具有超时、有限重试和总耗时预算，不会回退
到 Mock。生产配置仍默认使用 `mock`，完成长期稳定验证后再手动切换为 `tencent`。
单标的映射或解析失败不会影响同批正常行情，系统级故障也不会导致长期服务退出。

腾讯源当前保留供应方返回的成交量和成交额原始值，不进行未经验证的单位转换。
真实行情响应使用供应方时间，不能用本机请求时间代替。

告警规则位于 `config/rules.yaml`。阈值统一使用正数幅度，由 `direction` 表达上涨或
下跌；窗口历史与告警状态仅保存在内存，服务重启后会丢失。规则匹配时生成
`AlertEvent`，并依次执行结构化日志、告警持久化和已启用的通知渠道。

每条成功行情会写入 SQLite 的 `quote_snapshot` 表，每个新产生的告警会写入
`alert_event` 表。Decimal 使用文本保存，时间统一保存为 UTC ISO 8601；同代码、同
行情时间的快照采用 last-write-wins。存储故障会记录 ERROR，但不会阻断规则计算或
告警日志，避免数据库临时故障造成实时告警遗漏。

企业微信机器人默认关闭。启用时将 `notify.wechat.enabled` 改为 `true`，并通过
`LUMINA_WECHAT_URL` 环境变量提供 webhook。密钥不会写入 YAML 或日志。
通知采用同步有限重试，并由 `max_total_seconds` 限制单条通知占用调度线程的总时间；
通知失败不会影响后续告警。

## 质量检查

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest
```

## Ubuntu 部署

代码安装到 `/opt/lumina`，配置保存在 `/etc/lumina`，数据库位于
`/var/lib/lumina`，在线备份位于 `/var/backups/lumina`。首次部署先创建专用用户和目录：

```bash
sudo useradd --system --home /opt/lumina --shell /usr/sbin/nologin lumina
sudo install -d -o lumina -g lumina /opt/lumina /var/lib/lumina /var/log/lumina
sudo install -d -m 750 -o lumina -g lumina /var/backups/lumina
sudo install -d -m 750 -o root -g lumina /etc/lumina
```

仅在配置文件尚不存在时，从仓库模板安装。升级时不要用模板覆盖 `/etc/lumina`：

```bash
test -e /etc/lumina/settings.yaml || sudo install -m 640 -o root -g lumina config/settings.production.yaml /etc/lumina/settings.yaml
test -e /etc/lumina/stocks.yaml || sudo install -m 640 -o root -g lumina config/stocks.yaml /etc/lumina/stocks.yaml
test -e /etc/lumina/rules.yaml || sudo install -m 640 -o root -g lumina config/rules.yaml /etc/lumina/rules.yaml
test -e /etc/lumina/lumina.env || sudo install -m 600 -o root -g root /dev/null /etc/lumina/lumina.env
```

以上四条安装配置的命令只在首次部署执行。后续应使用 `sudoedit` 审核和修改现有文件。
从旧版本升级时，必须把生产模板中的 `storage.retention` 和 `storage.backup` 节点人工
合并到现有 settings；不要整文件覆盖。缺少 `/var/backups/lumina` 配置或写权限时，
maintenance 会失败并保留全部行情，不会退化为无备份清理。
创建虚拟环境并安装当前提交后，记录实际部署版本：

```bash
python3.11 -m venv /opt/lumina/.venv
/opt/lumina/.venv/bin/pip install --upgrade pip
/opt/lumina/.venv/bin/pip install /opt/lumina/dist/lumina-0.1.0-py3-none-any.whl
LUMINA_RELEASE_SHA='REPLACE_WITH_FULL_40_CHARACTER_COMMIT_SHA'
printf '%s\n' "$LUMINA_RELEASE_SHA" | sudo tee /opt/lumina/DEPLOYED_COMMIT >/dev/null
sudo chown root:lumina /opt/lumina/DEPLOYED_COMMIT
sudo chmod 640 /opt/lumina/DEPLOYED_COMMIT
```

`LUMINA_RELEASE_SHA` 必须由构建或发布端从本次 wheel 对应的 Git 提交取得并传入，
服务器不依赖 `/opt/lumina` 是 Git 工作树。写入后应与发布记录中的完整 SHA 核对。
保留本次 wheel 和上一版 wheel。回滚时重新安装上一版 wheel，并把
`DEPLOYED_COMMIT` 更新为对应提交。不要删除或替换 `/var/lib/lumina/lumina.db`。

安装或更新 systemd 单元：

```bash
sudo cp deploy/systemd/lumina.service /etc/systemd/system/lumina.service
sudo cp deploy/systemd/lumina-maintenance.service /etc/systemd/system/lumina-maintenance.service
sudo cp deploy/systemd/lumina-maintenance.timer /etc/systemd/system/lumina-maintenance.timer
sudo systemctl daemon-reload
sudo systemctl enable --now lumina.service
sudo systemctl enable --now lumina-maintenance.timer
```

只有 systemd 单元发生变化时才需要 `daemon-reload`。主服务启动前只检查配置、日志和
数据目录权限以及 SQLite 连接，不检查腾讯或企业微信网络。连续启动失败超过限制后，
systemd 会停止快速重试，避免错误配置造成无限重启。

如需启用企业微信，先轮换所有曾暴露的 webhook，再使用 `sudoedit
/etc/lumina/lumina.env` 写入：

```bash
LUMINA_WECHAT_URL='REPLACE_WITH_ROTATED_WEBHOOK'
```

YAML 只能保存 `webhook_env: LUMINA_WECHAT_URL`，不得保存真实 URL。环境文件保持
`0600 root:root`；验证时只能检查变量是否存在，不能打印变量内容。腾讯和数据库稳定
后才启用通知。

查看服务状态与日志：

```bash
systemctl status lumina.service
journalctl -u lumina.service -f
journalctl -u lumina-maintenance.service
systemctl list-timers lumina-maintenance.timer
cat /opt/lumina/DEPLOYED_COMMIT
```

systemd 会在进程异常退出后自动重启服务。正常停止时发送 `SIGTERM`，
Lumina 会结束调度循环并退出。

## SQLite 保留、备份与恢复

每日 03:30 左右由 `lumina-maintenance.timer` 启动独立 oneshot 进程。维护任务不会加入
行情调度线程，固定顺序为：

```text
SQLite backup API 在线备份 → quick_check → 清理行情 → checkpoint → 轮转备份
```

`quote_snapshot` 保留 30 天并以 5,000 条短事务分批清理；`alert_event` 暂不自动清理。
备份保留最近 14 份。备份或一致性检查失败时，本轮不会删除任何行情。运行中的 WAL
数据库禁止用文件复制命令直接备份，也不应每日执行 `VACUUM`。

部署后先手动验证维护任务：

```bash
sudo systemctl start lumina-maintenance.service
sudo systemctl status lumina-maintenance.service
sudo -u lumina /opt/lumina/.venv/bin/python -c "import sqlite3; c=sqlite3.connect('/var/backups/lumina/REPLACE.db'); print(c.execute('PRAGMA quick_check').fetchone()); c.close()"
```

恢复演练必须写到全新路径，不覆盖生产数据库。可在 Python 中调用
`app.storage.backup.restore_backup`，验证表、记录数量和 `PRAGMA quick_check` 后删除演练
副本。建议每月执行一次恢复演练。大批量清理后 SQLite 会复用空闲页；只有确需归还
磁盘空间时，才在停止主服务、确认空闲空间充足并完成备份后人工执行 `VACUUM`。

## Tencent 真实行情 smoke

仓库提供 `deploy/smoke` 下的独立配置。它只包含 `000001 INDEX`、`510300 ETF` 和
`600519 STOCK`，通知关闭，数据库写入 `/tmp/lumina-smoke/lumina.db`，不会修改正式
配置或正式数据库。先完成离线测试，再在服务器短时运行：

```bash
sudo -u lumina install -d /tmp/lumina-smoke/logs
sudo -u lumina env LUMINA_LOG_DIR=/tmp/lumina-smoke/logs \
  timeout --signal=TERM 20s /opt/lumina/.venv/bin/lumina \
  --settings /opt/lumina/deploy/smoke/settings.tencent.yaml \
  --stocks /opt/lumina/deploy/smoke/stocks.yaml \
  --rules /opt/lumina/deploy/smoke/rules.yaml
sudo -u lumina /opt/lumina/.venv/bin/python - <<'PY'
import sqlite3

connection = sqlite3.connect("/tmp/lumina-smoke/lumina.db")
try:
    rows = connection.execute(
        "SELECT code, price, quote_time, created_at "
        "FROM quote_snapshot ORDER BY code"
    ).fetchall()
    for row in rows:
        print(row)
finally:
    connection.close()
PY
```

检查三只标的的返回数量、价格、昨收、行情时间、成交量、成交额，以及 HTTP 重试和
`MarketSourceError` 日志。腾讯源
继续保留供应方 volume/turnover 原始语义。验证结束后可删除 `/tmp/lumina-smoke`，但
不得删除正式数据库或正式日志。

安全上线顺序：提交并发布 wheel，备份数据库，Mock 模式启动，执行独立 Tencent
smoke，显式切换正式配置为 Tencent，观察日志与数据库，最后轮换并启用企业微信。

## 模块职责

- `app/core`：配置、日志和周期调度。
- `app/market`：标准化行情模型、批量数据源协议、Mock 源及供应方实现。
- `app/market/factory.py`：根据配置创建行情源，拒绝未知或尚未实现的数据源。
- `app/market/symbols.py`：结合代码和标的类型映射腾讯沪深证券标识。
- `app/market/tencent_parser.py`：严格解析腾讯文本并转换为统一 Decimal 行情。
- `app/core/retry.py`：与 HTTP、行情和通知业务无关的同步重试预算。
- `app/market/collector.py`：批量采集、结构化日志和逐行情监控处理入口。
- `app/monitor`：内存行情历史、涨跌幅规则、边沿触发状态和告警事件模型。
- `app/notify/formatter.py`：将 `AlertEvent` 转换为通用 `MessagePayload`。
- `app/notify/notifier.py`：通知渠道协议和禁用状态实现。
- `app/notify/wechat.py`：企业微信同步发送、响应校验和有界重试。
- `app/storage/database.py`：SQLite 连接、事务边界和幂等表结构初始化。
- `app/storage/models.py`：领域模型到持久化记录的类型化转换。
- `app/storage/repository.py`：隔离行情快照与告警事件的 SQL 写入。
- `app/main.py`：依赖装配及服务生命周期。

Mock 行情源完全在本地生成可重复数据；只有将 `market.source` 显式设置为 `tencent`
后才会请求真实行情。新浪仍是未实现的扩展边界。只有显式启用企业微信并提供 webhook
后，通知模块才会访问企业微信网络接口。
