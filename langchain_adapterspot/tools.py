"""LangChain tools for the Power Adapter Label Reader API (AdapterSpot).

Docs: https://adapterspot.com/en/api/langchain/
"""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any, Literal, Optional, Type

import httpx
from langchain_core.tools import BaseTool, ToolException
from langchain_core.utils import secret_from_env
from pydantic import BaseModel, Field, SecretStr

DEFAULT_BASE_URL = "https://api.adapterspot.com"
MAX_IMAGE_BYTES = 3_700_000
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_KEY_HELP = (
    "Set the ADAPTERSPOT_API_KEY environment variable or pass api_key=. "
    "Get a free key at https://adapterspot.com/en/api/"
)


class _AdapterSpotBase(BaseTool):
    """Shared settings and HTTP handling for AdapterSpot tools."""

    api_key: Optional[SecretStr] = Field(
        default_factory=secret_from_env("ADAPTERSPOT_API_KEY", default=None)
    )
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 60.0
    handle_tool_error: bool = True

    def _headers(self) -> dict[str, str]:
        if not self.api_key or not self.api_key.get_secret_value():
            raise ToolException(_KEY_HELP)
        return {
            "X-API-Key": self.api_key.get_secret_value(),
            "User-Agent": "langchain-adapterspot",
        }

    @staticmethod
    def _result(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            raise ToolException(f"AdapterSpot API returned HTTP {response.status_code}")
        if response.status_code >= 400:
            message = data.get("message") or data.get("error") or "request failed"
            raise ToolException(f"AdapterSpot API error {response.status_code}: {message}")
        return json.dumps(data, ensure_ascii=False)


def _load_image(image: str, timeout: float) -> tuple[str, str]:
    """Return (base64 data, media type) for a local path, an http(s) URL or a data URL."""
    if image.startswith("data:image/"):
        header, _, data = image.partition(",")
        return data, header[5:].split(";")[0]
    if image.startswith(("http://", "https://")):
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(image)
        if resp.status_code >= 400:
            raise ToolException(f"Could not download the image (HTTP {resp.status_code})")
        raw = resp.content
        media_type = resp.headers.get("content-type", "").split(";")[0].strip()
    else:
        path = Path(image).expanduser()
        if not path.is_file():
            raise ToolException(f"Image not found: {image}")
        raw = path.read_bytes()
        media_type = mimetypes.guess_type(path.name)[0] or ""
    if len(raw) > MAX_IMAGE_BYTES:
        raise ToolException("Image is larger than ~3.7 MB; resize it (1600 px on the long side is plenty).")
    if media_type not in _IMAGE_TYPES:
        media_type = _sniff(raw)
    return base64.b64encode(raw).decode(), media_type


def _sniff(raw: bytes) -> str:
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    raise ToolException("Unsupported image type; use JPEG, PNG or WebP.")


class LabelReaderInput(BaseModel):
    """Input for AdapterSpotLabelReader."""

    image: str = Field(
        description="Photo of the power adapter label or the device's rating plate: a local file path, an http(s) URL or a data URL."
    )
    lang: Literal["en", "nl", "fr"] = Field(
        default="en", description="Language of the note."
    )


class AdapterSpotLabelReader(_AdapterSpotBase):
    """Read a power adapter label from a photo with the AdapterSpot API.

    Returns JSON with the output voltage, current, wattage, connector and polarity,
    and the requirements a replacement power supply must meet.

    Setup:
        .. code-block:: bash

            pip install langchain-adapterspot
            export ADAPTERSPOT_API_KEY="as_live_..."

    Instantiate:
        .. code-block:: python

            from langchain_adapterspot import AdapterSpotLabelReader

            tool = AdapterSpotLabelReader()

    Invoke:
        .. code-block:: python

            tool.invoke({"image": "adapter-label.jpg"})
    """

    name: str = "adapterspot_label_reader"
    description: str = (
        "Read the rating label of a power adapter (or the power input on a device's type plate) "
        "from a photo. Input: a local image path or URL. Returns JSON with output voltage, current, "
        "wattage, connector type and polarity, plus the requirements for a replacement power supply."
    )
    args_schema: Type[BaseModel] = LabelReaderInput

    def _payload(self, image: str, lang: str) -> dict[str, Any]:
        data, media_type = _load_image(image, self.timeout)
        return {"image": data, "media_type": media_type, "lang": lang}

    def _run(self, image: str, lang: str = "en", run_manager: Any = None) -> str:
        payload = self._payload(image, lang)
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/v1/label", headers=self._headers(), json=payload)
        return self._result(resp)

    async def _arun(self, image: str, lang: str = "en", run_manager: Any = None) -> str:
        payload = self._payload(image, lang)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/v1/label", headers=self._headers(), json=payload)
        return self._result(resp)


class PowerSupplyFinderInput(BaseModel):
    """Input for AdapterSpotPowerSupplyFinder."""

    voltage: Optional[float] = Field(default=None, description="Output voltage in volts, e.g. 12")
    current: Optional[float] = Field(default=None, description="Output current in amps, e.g. 5")
    power: Optional[float] = Field(default=None, description="Output power in watts, e.g. 60")
    connector: Optional[str] = Field(
        default=None, description="Connector id (b21, b25, b35, din4, usbc) or text such as '5.5x2.1'"
    )
    polarity: Optional[Literal["center_positive", "center_negative"]] = Field(default=None)


class AdapterSpotPowerSupplyFinder(_AdapterSpotBase):
    """Get the requirements for a replacement power supply from known ratings.

    Give at least two of voltage, current and power. Returns the exact voltage,
    minimum current and power, plug, polarity and plain-English rules. Does not
    count toward the free monthly quota.

    Invoke:
        .. code-block:: python

            from langchain_adapterspot import AdapterSpotPowerSupplyFinder

            AdapterSpotPowerSupplyFinder().invoke({"voltage": 12, "current": 5, "connector": "5.5x2.1"})
    """

    name: str = "adapterspot_power_supply_finder"
    description: str = (
        "Work out which power supply a device needs, given at least two of output voltage (V), "
        "current (A) and power (W), optionally the connector and polarity. Returns JSON with the "
        "required voltage, minimum current and power, plug, polarity and plain-English rules."
    )
    args_schema: Type[BaseModel] = PowerSupplyFinderInput

    @staticmethod
    def _params(**kwargs: Any) -> dict[str, Any]:
        return {k: v for k, v in kwargs.items() if v is not None}

    def _run(
        self,
        voltage: Optional[float] = None,
        current: Optional[float] = None,
        power: Optional[float] = None,
        connector: Optional[str] = None,
        polarity: Optional[str] = None,
        run_manager: Any = None,
    ) -> str:
        params = self._params(voltage=voltage, current=current, power=power, connector=connector, polarity=polarity)
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(f"{self.base_url}/v1/requirements", headers=self._headers(), params=params)
        return self._result(resp)

    async def _arun(
        self,
        voltage: Optional[float] = None,
        current: Optional[float] = None,
        power: Optional[float] = None,
        connector: Optional[str] = None,
        polarity: Optional[str] = None,
        run_manager: Any = None,
    ) -> str:
        params = self._params(voltage=voltage, current=current, power=power, connector=connector, polarity=polarity)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/v1/requirements", headers=self._headers(), params=params)
        return self._result(resp)
