"""LangChain standard unit tests for the tools."""

from typing import Type

from langchain_tests.unit_tests import ToolsUnitTests

from langchain_adapterspot import AdapterSpotLabelReader, AdapterSpotPowerSupplyFinder

KEY = "as_live_" + "0" * 48


class TestLabelReaderStandard(ToolsUnitTests):
    @property
    def tool_constructor(self) -> Type[AdapterSpotLabelReader]:
        return AdapterSpotLabelReader

    @property
    def tool_constructor_params(self) -> dict:
        return {"api_key": KEY}

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"image": "adapter-label.jpg", "lang": "en"}


class TestPowerSupplyFinderStandard(ToolsUnitTests):
    @property
    def tool_constructor(self) -> Type[AdapterSpotPowerSupplyFinder]:
        return AdapterSpotPowerSupplyFinder

    @property
    def tool_constructor_params(self) -> dict:
        return {"api_key": KEY}

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"voltage": 12, "current": 5, "connector": "5.5x2.1"}
