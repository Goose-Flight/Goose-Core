# Adding a Plugin

Plugins are the analysis engines that produce `ForensicFinding` objects from a `Flight`. This guide explains how to add a new plugin.

## 1. Create the plugin file

Create `src/goose/plugins/my_plugin.py`:

```python
"""My plugin — brief description."""
from __future__ import annotations
from typing import Any
from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# Thresholds — define as module-level DEFAULT_* constants for tuning profile parity
DEFAULT_MY_THRESHOLD = 42.0

class MyPlugin(Plugin):
    name = "my_plugin"
    description = "What this plugin checks"
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="my_plugin",
        name="My Plugin",
        version="1.0.0",
        author="Your Name",
        description="What this plugin checks",
        category=PluginCategory.HEALTH,
        supported_vehicle_types=["multirotor", "all"],
        required_streams=["battery"],      # plugin is skipped if these are empty
        optional_streams=["motors"],
        output_finding_types=["my_finding_type"],
        primary_stream="battery",          # main stream for EvidenceReference.stream_name
    )

    # DEFAULT_* constants mirror DEFAULT_CONFIG for tuning profile tests
    DEFAULT_MY_THRESHOLD = DEFAULT_MY_THRESHOLD

    DEFAULT_CONFIG: dict[str, Any] = {
        "my_threshold": DEFAULT_MY_THRESHOLD,
    }

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        cfg = {**self.DEFAULT_CONFIG, **config}
        threshold = float(cfg["my_threshold"])
        findings: list[Finding] = []

        if flight.battery.empty:
            return findings

        # ... your analysis logic ...

        # Pass finding (no issues):
        findings.append(Finding(
            plugin_name=self.name,
            title="My check passed",
            severity="pass",
            score=100,
            description="Everything looks fine.",
        ))

        return findings
```

## 2. Register the plugin

Open `src/goose/plugins/__init__.py` and add your plugin to `PLUGIN_REGISTRY`:

```python
from goose.plugins.my_plugin import MyPlugin

PLUGIN_REGISTRY: dict[str, Plugin] = {
    # ... existing plugins ...
    "my_plugin": MyPlugin(),
}
```

## 3. Key rules for `analyze()`

- **Return a Finding for every outcome** — including pass cases. Silent returns leave gaps in analysis history.
- **Include `timestamp_start` / `timestamp_end`** when you can. These populate `EvidenceReference.time_range_start/end` and improve timeline accuracy.
- **Include evidence dict** with key metrics. These become `ForensicFinding.supporting_metrics`.
- **Score means 0=worst, 100=best/pass.** Critical findings should have scores near 0; PASS findings should have scores 90–100.
- **Use `DEFAULT_CONFIG` + `config` merge** — always start with defaults and let config override. This enables tuning profiles.

## 4. DEFAULT_* constants (required)

Every plugin must define `DEFAULT_*` class-level constants that match the values in `DEFAULT_CONFIG`. The tuning profile test suite (`test_plugins/test_tuning_parity.py`) checks that every threshold in `DEFAULT_CONFIG` has a corresponding `DEFAULT_*` constant. This prevents silent drift between plugin code and tuning profile definitions.

```python
DEFAULT_VIBRATION_GOOD_MS2 = 15.0   # must match DEFAULT_CONFIG["vibration_good_ms2"]
```

## 5. The `forensic_analyze()` bridge

You do NOT need to implement `forensic_analyze()`. The base class handles it:
1. Checks `manifest.required_streams` — skips the plugin if any are empty.
2. Merges tuning profile thresholds into config.
3. Calls your `analyze()`.
4. Wraps each thin `Finding` into a `ForensicFinding` with an `EvidenceReference`.

## 6. Write tests

Create `tests/test_plugins/test_my_plugin.py` with at least:
- A test on a normal flight (no anomaly) — expect PASS finding.
- A test on an anomalous flight — expect CRITICAL or WARNING finding.
- Check that the `EvidenceReference` has the right `stream_name`.

See `tests/test_plugins/test_crash_detection.py` for examples.

## 7. Profile awareness (optional)

If you want your plugin to appear in a profile's `default_plugins` list, add it to the profile in `src/goose/forensics/profiles.py`. Profiles only bias execution order — they never change what findings your plugin emits.
