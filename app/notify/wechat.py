"""企业微信机器人通知边界。"""

from __future__ import annotations


class NotificationError(RuntimeError):
    """通知发送失败。"""


class WeChatNotifier:
    """企业微信机器人占位实现，暂不进行网络请求。"""

    def send(self, message: str) -> None:
        if not message.strip():
            raise ValueError("通知内容不能为空")
        raise NotificationError("企业微信通知尚未实现")
