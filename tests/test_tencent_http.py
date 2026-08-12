from io import BytesIO
from typing import Self, cast
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from app.market.tencent_http import (
    MAX_TENCENT_RESPONSE_BYTES,
    UrllibTencentHttpTransport,
)


def test_tencent_transport_uses_https_get_and_bounded_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def getcode(self) -> int:
            return 200

        def read(self, amount: int) -> bytes:
            captured["read_amount"] = amount
            return b"response"

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.market.tencent_http.urlopen", fake_urlopen)
    result = UrllibTencentHttpTransport().get(
        "https://qt.gtimg.cn/q=sh510300",
        timeout=3,
    )

    request = cast(Request, captured["request"])
    assert result.status_code == 200
    assert request.method == "GET"
    assert request.full_url.startswith("https://")
    assert request.get_header("User-agent") == "lumina/0.1"
    assert captured["timeout"] == 3
    assert captured["read_amount"] == MAX_TENCENT_RESPONSE_BYTES + 1


def test_tencent_transport_propagates_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: float) -> object:
        del request, timeout
        raise TimeoutError("timed out")

    monkeypatch.setattr("app.market.tencent_http.urlopen", fake_urlopen)

    with pytest.raises(TimeoutError, match="timed out"):
        UrllibTencentHttpTransport().get(
            "https://qt.gtimg.cn/q=sh510300",
            timeout=1,
        )


def test_tencent_transport_returns_http_error_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: object, timeout: float) -> object:
        del timeout
        url = cast(Request, request).full_url
        raise HTTPError(url, 503, "unavailable", None, BytesIO(b"temporary failure"))

    monkeypatch.setattr("app.market.tencent_http.urlopen", fake_urlopen)

    result = UrllibTencentHttpTransport().get(
        "https://qt.gtimg.cn/q=sh510300",
        timeout=1,
    )

    assert result.status_code == 503
    assert result.body == b"temporary failure"


def test_tencent_transport_rejects_non_https_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        UrllibTencentHttpTransport().get(
            "http://qt.gtimg.cn/q=sh510300",
            timeout=1,
        )
