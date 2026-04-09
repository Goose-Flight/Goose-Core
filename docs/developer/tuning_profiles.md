# Tuning Profiles

Tuning profiles control the numeric thresholds used by analysis plugins. They are separate from user profiles (which control UI presentation) and from feature gates (which control capability access).

## What They Control

`TuningProfile` provides per-plugin threshold sets. When `forensic_analyze()` runs:
1. It calls `tuning_profile.get_config_for_plugin(plugin_id)`.
2. If a config exists, its `thresholds.values` dict is merged into the plugin's `config` arg.
3. Explicit values in `config` take precedence over tuning-profile values.

This means tuning profiles provide defaults that can be overridden at the call site.

## Structure

```python
# src/goose/forensics/tuning.py
@dataclass
class ThresholdSet:
    values: dict[str, float | int | str]

@dataclass
class AnalyzerConfigProfile:
    plugin_id: str
    thresholds: ThresholdSet | None = None

@dataclass
class TuningProfile:
    profile_id: str
    version: str
    configs: list[AnalyzerConfigProfile]

    def get_config_for_plugin(self, plugin_id: str) -> AnalyzerConfigProfile | None: ...
    @classmethod
    def default(cls) -> TuningProfile: ...
```

## Default Profile

`TuningProfile.default()` returns the standard threshold set used by all current analysis runs. Its `profile_id` is `"default"` and it matches the `DEFAULT_*` constants defined in each plugin.

## Threshold Parity Test

`tests/test_plugins/test_tuning_parity.py` verifies that:
1. Every threshold key in a plugin's `DEFAULT_CONFIG` has a corresponding `DEFAULT_*` constant.
2. The default tuning profile's thresholds for each plugin match the plugin's `DEFAULT_CONFIG` values.

This prevents silent drift between plugin code and the tuning system.

## Persistence

The tuning profile used for each run is persisted to `analysis/tuning_profile.json` alongside the run's findings. This ensures replay and diff can reconstruct the exact thresholds that produced a given result.

## Extending

To add a new threshold for an existing plugin:
1. Add a `DEFAULT_MY_THRESHOLD` constant to the plugin.
2. Add `"my_threshold": DEFAULT_MY_THRESHOLD` to `DEFAULT_CONFIG`.
3. Update `TuningProfile.default()` to include the new threshold.
4. Update the parity test fixture if you have one.

To add a new tuning profile (e.g., "aggressive"):
1. Create a new `TuningProfile` with a different `profile_id`.
2. Set threshold values that differ from defaults.
3. Expose via `GET /api/cases/{id}/tuning-profile` or a new route.
