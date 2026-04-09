# Parser and Plugin Contract

## Parser Contract

Every parser must extend `BaseParser` and return a `ParseResult` — never raise.

```python
class BaseParser(ABC):
    format_name: str          # e.g. "ulog"
    file_extensions: list[str]  # e.g. [".ulg"]
    implemented: bool = True  # False for stubs

    def parse(self, filepath: Path) -> ParseResult: ...
    def can_parse(self, filepath: Path) -> bool: ...
```

`ParseResult` contains:
- `flight: Flight | None` — the canonical flight model (None on failure)
- `diagnostics: ParseDiagnostics` — always present; captures format confidence, stream coverage, warnings, errors
- `provenance: Provenance | None` — parser lineage (parser_name, parser_version, engine_version, flight_duration_sec, etc.)
- `success: bool`

`ParseDiagnostics` includes:
- `parser_confidence: float` — parse/data-quality confidence (0.0–1.0). NOT finding confidence, NOT hypothesis confidence.
- `confidence_scope: str = "parser_parse_quality"` — explicit scope label
- `stream_coverage: list[StreamCoverage]` — per-stream presence and row count
- `warnings: list[str]`, `errors: list[str]`
- `detected_format: str`, `parser_selected: str`

Stubs (`implemented = False`) return `ParseResult.failure()` with a clear error message. They never implicitly fail.

## Plugin Contract

Every plugin must extend `Plugin` and implement `analyze()`:

```python
class Plugin(ABC):
    name: str             # unique identifier e.g. "vibration"
    description: str
    version: str
    min_mode: str = "manual"
    manifest: PluginManifest

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]: ...
    def forensic_analyze(...) -> tuple[list[ForensicFinding], PluginDiagnostics]: ...
```

`PluginManifest` declares:
- `plugin_id: str` — unique plugin identifier
- `required_streams: list[str]` — if any stream is missing, the plugin is skipped (not crashed)
- `optional_streams: list[str]`
- `primary_stream: str` — the main telemetry stream this plugin analyzes; used for `EvidenceReference.stream_name`
- `trust_state: PluginTrustState` — `builtin_trusted`, `local_unsigned`, etc.
- `category: PluginCategory`

`forensic_analyze()` in `base.py`:
1. Checks required streams — if any are empty, returns a SKIPPED `PluginDiagnostics`.
2. Merges tuning profile thresholds into config.
3. Calls `analyze()`.
4. Converts thin `Finding` objects to `ForensicFinding` via the thin-finding bridge.
5. Returns `(list[ForensicFinding], PluginDiagnostics)`.

`PluginDiagnostics` captures per-run execution state: `executed`, `skipped`, `blocked`, `missing_streams`, `findings_emitted`, `execution_duration_ms`, `trust_state`.

## DEFAULT_* Constants

Every plugin should define `DEFAULT_*` constants alongside the `DEFAULT_CONFIG` dict so tuning profile tests can verify threshold parity without importing the full plugin config dict. Example:

```python
DEFAULT_VIBRATION_GOOD_MS2 = 15.0
DEFAULT_VIBRATION_WARNING_MS2 = 30.0
```

## Thin-Finding Bridge

The thin-finding bridge in `base.py:forensic_analyze()` converts `goose.core.finding.Finding` to `ForensicFinding`. Key rules:
- `evidence_id` comes from the case evidence item passed at call time.
- `stream_name` comes from `self.manifest.primary_stream`.
- `time_range_start/end` come from `thin.timestamp_start/end` (may be None if the plugin didn't compute them).
- `confidence` is `score / 100.0` (proxy until plugins declare their own confidence).
- The bridge never raises — JSON-unsafe evidence values are stringified.

## PLUGIN_REGISTRY

`src/goose/plugins/__init__.py` defines `PLUGIN_REGISTRY: dict[str, Plugin]` — a module-level dict of all registered plugins, keyed by `plugin.name`. This is the single source of truth for plugin discovery. The lifting layer uses it to resolve `primary_stream` for evidence reference construction.
