from __future__ import annotations

from io import BytesIO
import json
from typing import Any

import pytest

from dmw_experiments.studies.haiu_comparison.entrypoints import (
    lmstudio_model_proxy,
)


class _FakeResponse:
    status = 200

    def read(self) -> bytes:
        return b'{"data":[]}'

    def getheader(self, _name: str, default: str) -> str:
        return default


class _FakeConnection:
    requests: list[tuple[str, str, bytes | None, dict[str, str]]] = []
    destinations: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.destinations.append((args, kwargs))

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict[str, str],
    ) -> None:
        self.requests.append((method, path, body, headers))

    def getresponse(self) -> _FakeResponse:
        return _FakeResponse()

    def close(self) -> None:
        return None


def _handler() -> lmstudio_model_proxy.ProxyHandler:
    handler = object.__new__(lmstudio_model_proxy.ProxyHandler)
    handler.path = "/v1/models"
    handler.headers = {"Authorization": "Bearer local"}
    handler.wfile = BytesIO()
    handler.send_response = lambda _status: None
    handler.send_header = lambda _name, _value: None
    handler.end_headers = lambda: None
    handler.upstream_host = "windows-host"
    handler.upstream_port = 1235
    return handler


def test_get_relays_model_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeConnection.requests.clear()
    _FakeConnection.destinations.clear()
    monkeypatch.setattr(
        lmstudio_model_proxy.http.client,
        "HTTPConnection",
        _FakeConnection,
    )
    handler = _handler()

    handler.do_GET()

    assert _FakeConnection.requests == [
        (
            "GET",
            "/v1/models",
            None,
            {"Authorization": "Bearer local"},
        )
    ]
    assert handler.wfile.getvalue() == b'{"data":[]}'
    assert _FakeConnection.destinations == [
        (("windows-host", 1235), {"timeout": 3600})
    ]


def test_post_maps_catalogued_name_to_loaded_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeConnection.requests.clear()
    monkeypatch.setattr(
        lmstudio_model_proxy.http.client,
        "HTTPConnection",
        _FakeConnection,
    )
    handler = _handler()
    request_body = json.dumps(
        {"model": "qwen/qwen3.6-27b", "messages": []}
    ).encode()
    handler.path = "/v1/chat/completions"
    handler.headers["Content-Length"] = str(len(request_body))
    handler.rfile = BytesIO(request_body)

    handler.do_POST()

    method, path, body, headers = _FakeConnection.requests[0]
    assert method == "POST"
    assert path == "/v1/chat/completions"
    assert body is not None
    assert json.loads(body)["model"] == "qwen/qwen3.6-27b"
    assert headers == {
        "Content-Type": "application/json",
        "Authorization": "Bearer local",
    }


@pytest.mark.parametrize(
    "model_alias",
    ("qwen3.6-27b", "qwen/qwen3.6-27b"),
)
def test_post_maps_catalogued_alias_to_loaded_variant(
    monkeypatch: pytest.MonkeyPatch,
    model_alias: str,
) -> None:
    _FakeConnection.requests.clear()
    monkeypatch.setattr(
        lmstudio_model_proxy.http.client,
        "HTTPConnection",
        _FakeConnection,
    )
    request_body = f'{{"model":"{model_alias}","messages":[]}}'.encode()
    handler = _handler()
    handler.path = "/v1/chat/completions"
    handler.headers = {
        "Authorization": "Bearer local",
        "Content-Length": str(len(request_body)),
    }
    handler.rfile = BytesIO(request_body)

    handler.do_POST()

    method, request_path, body, _headers = _FakeConnection.requests[0]
    assert method == "POST"
    assert request_path == "/v1/chat/completions"
    assert body is not None
    assert b'"model": "qwen/qwen3.6-27b"' in body
