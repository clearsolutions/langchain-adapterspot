# langchain-adapterspot

LangChain tools for the [AdapterSpot Power Supply Identifier API](https://adapterspot.com/en/api/).

- **`AdapterSpotLabelReader`**: send a photo of a power adapter label (or the rating plate on a device) and get the output voltage, current, wattage, connector type and polarity back as JSON, plus the power supply that fits.
- **`AdapterSpotPowerSupplyFinder`**: give the ratings (at least two of volts, amps and watts, optionally connector and polarity) and get the matching power supplies.

The label reader combines an AI vision model with the AdapterSpot connector library and catalog of verified power supplies for network and NAS equipment.

Full guide: <https://adapterspot.com/en/api/langchain/>

## Install

```bash
pip install langchain-adapterspot
```

## API key

Get a free key at <https://adapterspot.com/en/api/> (10 label reads per month; power-supply lookups are free), then:

```bash
export ADAPTERSPOT_API_KEY="as_live_..."
```

You can also pass `api_key="..."` to each tool.

## Use the tools directly

```python
from langchain_adapterspot import AdapterSpotLabelReader, AdapterSpotPowerSupplyFinder

reader = AdapterSpotLabelReader()
print(reader.invoke({"image": "adapter-label.jpg"}))  # local path, http(s) URL or data URL

finder = AdapterSpotPowerSupplyFinder()
print(finder.invoke({"voltage": 12, "current": 5, "connector": "5.5x2.1"}))
```

Both tools return a JSON string. Errors (missing key, quota used up, unreadable photo) come back as a readable message instead of an exception, so an agent can react to them.

## Use them in an agent

```python
from langchain.agents import create_agent
from langchain_adapterspot import AdapterSpotLabelReader, AdapterSpotPowerSupplyFinder

agent = create_agent(
    model="anthropic:claude-sonnet-5-5",
    tools=[AdapterSpotLabelReader(), AdapterSpotPowerSupplyFinder()],
)
result = agent.invoke(
    {"messages": [{"role": "user", "content": "Which power supply do I need? The label photo is ./nas-adapter.jpg"}]}
)
print(result["messages"][-1].content)
```

## Output (label reader)

```json
{
  "readable": true,
  "confidence": "high",
  "output": {"voltage_v": 12, "current_a": 5, "power_w": 60, "computed_field": null, "polarity": "center_positive"},
  "connector": {"id": null, "name": null, "printed": null, "seen_in_photo": "not_visible"},
  "match": {"exact": false, "power_supplies": [{"name": "Synology DS211j power supply (12V DC, 60W)", "voltage_v": 12, "current_a": 5, "url": "https://adapterspot.com/en/synology-ds211j-power-supply/", "ships_to": ["BE", "NL"]}]},
  "usage": {"month": "2026-11", "label_reads_used": 1, "label_reads_quota": 10, "label_reads_left": 9}
}
```

See the [API docs](https://adapterspot.com/en/api/) for every field.

## Development

```bash
pip install -e ".[test]"
pytest
```

## License

MIT. Maintained by AdapterSpot (Clear Solutions BV, Essen, Belgium). Support: info@adapterspot.com
