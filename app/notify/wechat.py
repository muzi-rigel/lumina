"""企业微信机器人同步发送与有界重试。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.monitor.model import AlertEvent
from app.notify.formatter import AlertFormatter, MessageFormat, MessagePayload

MAX_RESPONSE_BYTES = 65_536


class NotificationError(RuntimeError):
    """通知发送经过有限重试后仍失败。"""


@dataclass(frozen=True, slots=True)
class HttpResult:
    status_code: int
    body: bytes


class HttpTransport(Protocol):
    def post_json(self, url: str, payload: dict[str, object], timeout: float) -> HttpResult:
        """发送 JSON，并返回有限大小的响应。"""


class UrllibHttpTransport:
    """只使用 Python 标准库的 HTTP 传输实现。"""

    def post_json(self, url: str, payload: dict[str, object], timeout: float) -> HttpResult:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return HttpResult(response.getcode(), response.read(MAX_RESPONSE_BYTES + 1))
        except HTTPError as exc:
            return HttpResult(exc.code, exc.read(MAX_RESPONSE_BYTES + 1))


def _wechat_payload(payload: MessagePayload) -> dict[str, object]:
    if payload.format is MessageFormat.MARKDOWN:
        return {"msgtype": "markdown", "markdown": {"content": payload.content}}
    if payload.format is MessageFormat.TEXT:
        return {"msgtype": "text", "text": {"content": payload.content}}
    raise NotificationError(f"企业微信不支持消息格式：{payload.format}")


class WeChatNotifier:
    """在最大尝试次数和总耗时预算内同步发送机器人消息。"""

    def __init__(
        self,
        webhook_url: str,
        formatter: AlertFormatter,
        timeout_seconds: float,
        max_attempts: int,
        retry_backoff_seconds: float,
        max_total_seconds: float,
        transport: HttpTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._webhook_url = webhook_url
        self._formatter = formatter
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._backoff = retry_backoff_seconds
        self._max_total = max_total_seconds
        self._transport = transport or UrllibHttpTransport()
        self._sleeper = sleeper
        self._monotonic = monotonic

    @staticmethod
    def _response_error(result: HttpResult) -> tuple[NotificationError | None, bool]:
        if result.status_code == 429 or result.status_code >= 500:
            return NotificationError(f"企业微信 HTTP 响应异常：{result.status_code}"), True
        if not 200 <= result.status_code < 300:
            return NotificationError(f"企业微信 HTTP 响应异常：{result.status_code}"), False
        if len(result.body) > MAX_RESPONSE_BYTES:
            return NotificationError("企业微信响应超过大小限制"), True
        try:
            response: object = json.loads(result.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return NotificationError("企业微信响应不是有效 JSON"), True
        if not isinstance(response, dict):
            return NotificationError("企业微信响应结构非法"), True
        if response.get("errcode") == 0:
            return None, False
        errcode = response.get("errcode", "unknown")
        errmsg = response.get("errmsg", "unknown")
        return NotificationError(f"企业微信业务错误 errcode={errcode} errmsg={errmsg}"), True

    def _remaining(self, started_at: float) -> float:
        return self._max_total - (self._monotonic() - started_at)

    def send(self, alert: AlertEvent) -> None:
        payload = _wechat_payload(self._formatter.format(alert))
        started_at = self._monotonic()
        last_error = NotificationError("企业微信通知未发送")

        for attempt in range(1, self._max_attempts + 1):
            remaining = self._remaining(started_at)
            if remaining <= 0:
                raise NotificationError("企业微信通知超过最大总耗时") from last_error
            try:
                result = self._transport.post_json(
                    self._webhook_url,
                    payload,
                    timeout=min(self._timeout, remaining),
                )
                error, retryable = self._response_error(result)
            except (OSError, TimeoutError, URLError) as exc:
                error = NotificationError(f"企业微信网络请求失败：{type(exc).__name__}")
                retryable = True
            if error is None:
                return
            last_error = error
            if not retryable or attempt == self._max_attempts:
                raise error

            delay = self._backoff * (2 ** (attempt - 1))
            remaining = self._remaining(started_at)
            if delay >= remaining:
                raise NotificationError("企业微信通知超过最大总耗时") from last_error
            if delay > 0:
                self._sleeper(delay)

        raise last_error
