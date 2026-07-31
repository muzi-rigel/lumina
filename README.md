# Lumina

Lumina 是一个长期运行的 A 股智能监控与研究系统。目前仓库仅包含生产服务基础框架，
尚未实现行情采集、异动规则或消息发送。

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
.venv/bin/lumina --settings config/settings.yaml --stocks config/stocks.yaml
```

按 `Ctrl+C` 后，服务会完成当前任务并安全停止。SQLite 数据默认写入
`data/lumina.db`，该目录中的运行数据不会提交到 Git。

启动时会检查两个配置文件、日志目录、数据目录和配置时区下的系统时间。
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

## 质量检查

```bash
.venv/bin/ruff check .
.venv/bin/mypy app
.venv/bin/pytest
```

## Ubuntu 部署

建议代码安装到 `/opt/lumina`，配置保存到
`/etc/lumina/settings.yaml` 和 `/etc/lumina/stocks.yaml`。生产模板已将数据库设置为
`/var/lib/lumina/lumina.db`。

```bash
sudo useradd --system --home /opt/lumina --shell /usr/sbin/nologin lumina
sudo install -d -o lumina -g lumina /opt/lumina /etc/lumina
sudo cp config/settings.production.yaml /etc/lumina/settings.yaml
sudo cp config/stocks.yaml /etc/lumina/stocks.yaml
sudo cp deploy/systemd/lumina.service /etc/systemd/system/lumina.service
sudo systemctl daemon-reload
sudo systemctl enable --now lumina.service
```

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
- `app/monitor`：监控引擎和规则接口。
- `app/notify`：企业微信通知。
- `app/storage`：SQLite 连接和事务边界。
- `app/main.py`：依赖装配及服务生命周期。

当前 Mock 行情源完全在本地生成可重复数据；新浪、腾讯和企业微信模块均为明确的扩展
边界，不会发起外部请求。
