# Profile System Architecture

## What Profiles Are

Profiles (`src/goose/forensics/profiles.py`) are data-driven configuration blobs that tailor the UI and reports for a given user class without forking the forensic engine. Every profile produces the same canonical `ForensicFinding`, `Hypothesis`, and `AnalysisRun` output — only presentation and emphasis differ.

## What Profiles Change

- **Default plugins list** — which plugins are shown first and emphasized
- **Secondary / deprioritized plugins** — which plugins are de-emphasized
- **Findings sort priority** — severity ordering in result views
- **Hypothesis priority** — which hypothesis categories appear first
- **Wording pack** — terminology used in reports ("Pilot" vs "Operator", "Run" vs "Sortie", etc.)
- **Visible case fields** — which metadata fields are shown prominently
- **Chart presets** — which telemetry charts appear first in the GUI

## What Profiles DO NOT Change

- Parser logic — same parser runs for every profile
- Plugin analysis logic — same plugin code runs for every profile
- ForensicFinding content — findings are identical regardless of profile
- Hypothesis generation rules — same lifting.py logic for every profile
- Evidence integrity — same SHA-256/SHA-512 hashing
- Audit trail — same append-only log format
- Replay semantics — replay records profile_id but does not use it to filter

## Profile IDs

Seven profiles are defined in `PROFILE_CONFIGS`:

| profile_id | User Class |
|------------|-----------|
| `racer` | FPV racers, performance tuners |
| `research` | Academic and research labs |
| `shop_repair` | Drone repair shops |
| `factory_qa` | Manufacturing QA / acceptance |
| `gov_mil` | Public safety, mission operators |
| `advanced` | Power users — no defaults |
| `default` | General use — balanced defaults |

## Architecture

```
ProfileConfig (profiles.py)
  |-- profile_id
  |-- WordingPack (profile-specific labels)
  |-- default_plugins: list[str]   (run first)
  |-- secondary_plugins: list[str]
  |-- deprioritized_plugins: list[str] (run last)
  |-- findings_sort_priority: list[str]
  |-- hypothesis_priority: list[str]
  |-- visible_case_fields: list[str]
  |-- chart_presets: list[str]
  |-- to_dict() → serializable for /api/profiles
```

`get_profile(profile_id)` returns the `ProfileConfig` for the given ID, defaulting to `default` for unknown IDs.

## Runtime Flow

At `POST /api/cases/{id}/analyze`:
1. Active profile resolved from `case.profile` (defaults to `"default"`).
2. `get_profile()` returns `ProfileConfig`.
3. Plugin execution order is built: `primary_ids + secondary_ids + remaining + deprioritized`.
4. `plugin.forensic_analyze()` is called in that order.
5. Findings are sorted by the profile's `findings_sort_priority`.
6. Hypotheses are sorted by the profile's `hypothesis_priority`.
7. `profile_id` is recorded in `AnalysisRun.profile_id` and `plugin_diagnostics.json`.

## Wording Packs

`WordingPack` provides profile-specific label substitutions used in report generators (`reports.py`). Report generators call `get_profile(profile_id)` and use `profile_cfg.wording` to select the right label for each context. The underlying finding data is always the same — only the surface-level labels differ.

## Profile vs Product Behavior

Profiles are NOT product feature gates. Feature gates (`features.py`) control which capabilities are available at a given entitlement tier (OSS_CORE, Local_Pro, etc.). Profiles only control presentation for authenticated users within their tier.
