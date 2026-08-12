from collections.abc import Mapping

import pytest

from app.core.errors import ConfigError
from app.core.notify_config import WeChatSettings, parse_notify
from app.notify.factory import NotifierCreationError, create_notifier
from app.notify.notifier import NoopNotifier
from app.notify.wechat import WeChatNotifier


def _root(**overrides: object) -> Mapping[str, object]:
    values: dict[str, object] = {
        "enabled": False,
        "webhook_env": "LUMINA_WECHAT_URL",
        "timeout_seconds": 5,
        "max_attempts": 3,
        "retry_backoff_seconds": 1,
        "max_total_seconds": 15,
    }
    values.update(overrides)
    return {"notify": {"wechat": values}}


def test_notify_config_loads_bounded_retry_settings() -> None:
    settings = parse_notify(_root()).wechat

    assert settings.webhook_env == "LUMINA_WECHAT_URL"
    assert settings.timeout_seconds == 5
    assert settings.max_attempts == 3
    assert settings.retry_backoff_seconds == 1
    assert settings.max_total_seconds == 15


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("webhook_env", "invalid-name", "有效的环境变量名"),
        ("timeout_seconds", 0, "大于 0"),
        ("timeout_seconds", float("inf"), "有限数值"),
        ("max_attempts", 0, "1 到 5"),
        ("max_attempts", 6, "1 到 5"),
        ("retry_backoff_seconds", -1, "非负有限数值"),
        ("max_total_seconds", 0, "大于 0"),
    ],
)
def test_notify_config_rejects_unbounded_or_invalid_values(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_notify(_root(**{field: value}))


def test_notify_config_rejects_unknown_field() -> None:
    with pytest.raises(ConfigError, match="未知字段"):
        parse_notify(_root(retries=3))


def test_disabled_notifier_does_not_require_environment_secret() -> None:
    settings = parse_notify(_root(enabled=False)).wechat

    assert isinstance(create_notifier(settings, environ={}), NoopNotifier)


def test_enabled_notifier_requires_environment_secret() -> None:
    settings = parse_notify(_root(enabled=True)).wechat

    with pytest.raises(NotifierCreationError, match="环境变量"):
        create_notifier(settings, environ={})


@pytest.mark.parametrize("url", ["http://example.test/hook", "not-a-url"])
def test_enabled_notifier_requires_https_webhook(url: str) -> None:
    settings = parse_notify(_root(enabled=True)).wechat

    with pytest.raises(NotifierCreationError, match="HTTPS") as error:
        create_notifier(settings, environ={settings.webhook_env: url})

    assert url not in str(error.value)


def test_enabled_notifier_resolves_webhook_only_from_environment() -> None:
    settings = WeChatSettings(
        enabled=True,
        webhook_env="LUMINA_WECHAT_URL",
        timeout_seconds=5,
        max_attempts=3,
        retry_backoff_seconds=1,
        max_total_seconds=15,
    )

    notifier = create_notifier(
        settings,
        environ={settings.webhook_env: "https://example.test/webhook?key=secret"},
    )

    assert isinstance(notifier, WeChatNotifier)
