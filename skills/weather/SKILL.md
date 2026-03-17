---
name: weather
description: "Get weather info via wttr.in"
emoji: ☔
metadata: {"requires": {"bins": ["curl"]}}
---

# Weather Skill

Get current weather and forecasts.

## Commands

### Current Weather
```bash
curl "wttr.in/London?format=3"
```

### Forecast
```bash
curl "wttr.in/London?format=v2"
```
