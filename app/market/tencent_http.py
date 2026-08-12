"""腾讯行情源使用的标准库 HTTPS GET 传输。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

MAX_TENCENT_RESPONSE_BYTES = 512 * 1024


@dataclass(frozen=True, slots=True)
class TencentHttpResult:
    status_code: int
    body: bytes


class TencentHttpTransport(Protocol):
    def get(self, url: str, timeout: float) -> TencentHttpResult:
        """执行一次有限响应大小的 HTTPS GET。"""


class UrllibTencentHttpTransport:
    def get(self, url: str, timeout: float) -> TencentHttpResult:
        if not url.startswith("https://"):
            raise ValueError("腾讯行情请求只允许使用 HTTPS")
        request = Request(
            url,
            headers={
                "Accept": "text/plain,*/*;q=0.8",
                "User-Agent": "lumina/0.1",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return TencentHttpResult(
                    response.getcode(),
                    response.read(MAX_TENCENT_RESPONSE_BYTES + 1),
                )
        except HTTPError as exc:
            return TencentHttpResult(
                exc.code,
                exc.read(MAX_TENCENT_RESPONSE_BYTES + 1),
            )
