# Profile Configuration

This document explains how `ProfileConfig` works, how wording packs are used, and how to add or modify profiles.

## ProfileConfig Fields

```python
@dataclass
class ProfileConfig:
    profile_id: str                    # e.g. "racer", "gov_mil", "default"
    name: str                          # display name
    description: str
    wording: WordingPack               # label substitutions for reports/UI
    default_plugins: list[str]         # plugin_ids to run first
    secondary_plugins: list[str]       # run after primary
    deprioritized_plugins: list[str]   # run last (still run)
    findings_sort_priority: list[str]  # severity ordering for results view
    hypothesis_priority: list[str]     # hypothesis category ordering
    visible_case_fields: list[str]     # metadata fields to show prominently
    chart_presets: list[str]           # which telemetry charts appear first
```

## WordingPack Fields

```python
@dataclass
class WordingPack:
    profile_id: str
    workflow_label: str    # "Run" | "Case" | "Sortie" | "Test"
    event_label: str       # "Crash" | "Anomaly" | "Mishap" | "Incident"
    operator_label: str    # "Pilot" | "Operator" | "Technician" | "Tester"
    platform_label: str    # "Quad" | "UAV" | "UAS" | "Aircraft"
    analysis_label: str    # "Check" | "Analysis" | "Investigation" | "Inspection"
    summary_heading: str   # heading used at top of reports
```

## How Wording Flows into Reports

Report generators in `reports.py` call:
```python
profile_cfg = get_profile(profile_id)
wording: WordingPack = profile_cfg.wording
```

Then use `wording.event_label`, `wording.operator_label`, etc. to construct report text. The underlying finding data is never changed — only the surface text adapts.

## Plugin Ordering

At analysis time (`POST /api/cases/{id}/analyze`):

```
ordered_plugin_ids = (
    primary_ids      # from profile.default_plugins, in declaration order
    + secondary_ids  # from profile.secondary_plugins
    + remaining      # anything not in any list, in PLUGIN_REGISTRY order
    + deprioritized  # from profile.deprioritized_plugins
)
```

If `profile.default_plugins` is empty (e.g., the `advanced` profile), all plugins run in `PLUGIN_REGISTRY` order without bias.

## Plugin Ordering Does NOT Affect Findings

Plugins are stateless — they each see the same `Flight` object. The order in which they run does not change what any individual plugin finds. It only changes the order findings appear in responses and persisted artifacts.

## Adding a New Profile

1. Add a new `ProfileConfig(...)` entry to `PROFILE_CONFIGS` in `src/goose/forensics/profiles.py`.
2. Add the profile_id to the `UserProfile` enum if you want formal validation.
3. The profile becomes available via `GET /api/profiles` and the profile selector in the GUI immediately.

## get_profile() Fallback

`get_profile(profile_id)` returns the matching `ProfileConfig` from `PROFILE_CONFIGS`. If the profile_id is unknown, it returns the `default` profile. It never raises.

## Case Profile Persistence

When a case is created, the profile is stored in `case.profile` (written to `case.json`). Analysis runs record `profile_id` in `AnalysisRun.profile_id` and `plugin_diagnostics.json`. This means you can reconstruct which profile produced a given run — useful for replay and for understanding why plugin ordering differs between runs.
