# Lumina

Lumina 是一个长期运行的 A 股智能监控与研究系统。当前已具备 Mock 批量行情采集、
短期内存行情窗口，以及日内和指定窗口涨跌幅告警；尚未接入真实行情和消息发送。

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

行情采集配置位于 `settings.yaml`：

```yaml
market:
  source: mock
  interval_seconds: 5
  mock:
    seed: 42
```

当前只有 `mock` 可运行。配置为 `sina` 或 `tencent` 时，服务会在启动阶段明确
报错，不会回退到 Mock。每个周期对所有启用标的执行一次批量查询，单标的失败或
系统级行情源故障不会导致长期服务退出。

告警规则位于 `config/rules.yaml`。阈值统一使用正数幅度，由 `direction` 表达上涨或
下跌；窗口历史与告警状态仅保存在内存，服务重启后会丢失。规则匹配时生成
`AlertEvent`，并依次执行结构化日志、告警持久化和已启用的通知渠道。

每条成功行情会写入 SQLite 的 `quote_snapshot` 表，每个新产生的告警会写入
`alert_event` 表。Decimal 使用文本保存，时间统一保存为 UTC ISO 8601；同代码、同
行情时间的快照采用 last-write-wins。存储故障会记录 ERROR，但不会阻断规则计算或
告警日志，避免数据库临时故障造成实时告警遗漏。

企业微信机器人默认关闭。启用时将 `notify.wechat.enabled` 改为 `true`，并通过
`LUMINA_WECHAT_WEBHOOK_URL` 环境变量提供 webhook。密钥不会写入 YAML 或日志。
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

建议代码安装到 `/opt/lumina`，配置保存到
`/etc/lumina/settings.yaml`、`/etc/lumina/stocks.yaml` 和
`/etc/lumina/rules.yaml`。生产模板已将数据库设置为 `/var/lib/lumina/lumina.db`。

```bash
sudo useradd --system --home /opt/lumina --shell /usr/sbin/nologin lumina
sudo install -d -o lumina -g lumina /opt/lumina /etc/lumina
sudo cp config/settings.production.yaml /etc/lumina/settings.yaml
sudo cp config/stocks.yaml /etc/lumina/stocks.yaml
sudo cp config/rules.yaml /etc/lumina/rules.yaml
sudo install -m 600 -o root -g root /dev/null /etc/lumina/lumina.env
sudo cp deploy/systemd/lumina.service /etc/systemd/system/lumina.service
sudo systemctl daemon-reload
sudo systemctl enable --now lumina.service
```

如需启用企业微信，在 `/etc/lumina/lumina.env` 中设置：

```bash
LUMINA_WECHAT_WEBHOOK_URL=https://example.invalid/cgi-bin/webhook/send?key=REPLACE_ME
```

该文件应保持仅 root 可读。示例 URL 不能直接使用，必须替换为实际机器人 webhook。

查看服务状态与日志：

```bash
systemctl status lumina.service
journalctl -u lumina.service -f
```

systemd 会在进程异常退出后自动重启服务。正常停止时发送 `SIGTERM`，
Lumina 会结束调度循环并退出。

## 模块职责

- `app/core`：配置、日志和周期调度。
- `app/market`：标准化行情模型、批量数据源协议、Mock 源及供应方实现。
- `app/market/factory.py`：根据配置创建行情源，拒绝未知或尚未实现的数据源。
- `app/market/collector.py`：批量采集、结构化日志和逐行情监控处理入口。
- `app/monitor`：内存行情历史、涨跌幅规则、边沿触发状态和告警事件模型。
- `app/notify/formatter.py`：将 `AlertEvent` 转换为通用 `MessagePayload`。
- `app/notify/notifier.py`：通知渠道协议和禁用状态实现。
- `app/notify/wechat.py`：企业微信同步发送、响应校验和有界重试。
- `app/storage/database.py`：SQLite 连接、事务边界和幂等表结构初始化。
- `app/storage/models.py`：领域模型到持久化记录的类型化转换。
- `app/storage/repository.py`：隔离行情快照与告警事件的 SQL 写入。
- `app/main.py`：依赖装配及服务生命周期。

当前 Mock 行情源完全在本地生成可重复数据；新浪和腾讯模块仍为明确的扩展边界，不会
发起外部请求。只有显式启用企业微信并提供 webhook 后，通知模块才会访问网络。
