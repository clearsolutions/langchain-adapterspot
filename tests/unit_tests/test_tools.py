import base64
import json

import httpx
import pytest
from langchain_core.tools import ToolException

from langchain_adapterspot import AdapterSpotLabelReader, AdapterSpotPowerSupplyFinder
from langchain_adapterspot.tools import _load_image

KEY = "as_live_" + "0" * 48
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def api(monkeypatch):
    """Route all httpx calls to a fake API and record the requests."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("X-API-Key") != KEY:
            return httpx.Response(401, json={"error": "unauthorized", "message": "bad key"})
        if request.url.path == "/v1/label":
            return httpx.Response(200, json={"readable": True, "output": {"voltage_v": 12}})
        if request.url.path == "/v1/requirements":
            return httpx.Response(200, json={"requirements": {"voltage_v": 12, "complete": False}})
        return httpx.Response(404, json={"error": "not_found"})

    transport = httpx.MockTransport(handler)
    real_client, real_async = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=transport, **kw))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_async(transport=transport, **kw))
    return seen


def test_label_reader_sends_base64_and_type(api, tmp_path):
    img = tmp_path / "label.png"
    img.write_bytes(PNG)
    out = json.loads(AdapterSpotLabelReader(api_key=KEY).invoke({"image": str(img)}))
    assert out["readable"] is True
    body = json.loads(api[0].content)
    assert body["media_type"] == "image/png"
    assert base64.b64decode(body["image"]) == PNG
    assert body["lang"] == "en"


async def test_label_reader_async(api, tmp_path):
    img = tmp_path / "label.png"
    img.write_bytes(PNG)
    out = json.loads(await AdapterSpotLabelReader(api_key=KEY).ainvoke({"image": str(img), "lang": "nl"}))
    assert out["output"]["voltage_v"] == 12
    assert json.loads(api[0].content)["lang"] == "nl"


def test_finder_drops_empty_params(api):
    out = json.loads(AdapterSpotPowerSupplyFinder(api_key=KEY).invoke({"voltage": 12, "current": 5}))
    assert out["requirements"]["voltage_v"] == 12
    assert api[0].url.path == "/v1/requirements"
    assert dict(api[0].url.params) == {"voltage": "12.0", "current": "5.0"}


def test_api_error_becomes_tool_message(api):
    # handle_tool_error=True: the agent gets the error text instead of an exception
    out = AdapterSpotPowerSupplyFinder(api_key="as_live_" + "1" * 48).invoke({"voltage": 12, "current": 5})
    assert "401" in out and "bad key" in out


def test_missing_key(monkeypatch):
    monkeypatch.delenv("ADAPTERSPOT_API_KEY", raising=False)
    out = AdapterSpotPowerSupplyFinder().invoke({"voltage": 12, "current": 5})
    assert "ADAPTERSPOT_API_KEY" in out


def test_data_url_and_sniffing(tmp_path):
    data = base64.b64encode(PNG).decode()
    assert _load_image(f"data:image/png;base64,{data}", 5) == (data, "image/png")
    odd = tmp_path / "label.bin"
    odd.write_bytes(PNG)
    assert _load_image(str(odd), 5)[1] == "image/png"
    with pytest.raises(ToolException):
        _load_image(str(tmp_path / "missing.jpg"), 5)
