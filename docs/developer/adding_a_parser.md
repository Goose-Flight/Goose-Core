# Adding a Parser

Parsers convert raw flight log files into the canonical `Flight` model. This guide explains how to implement a new parser.

## Contract

Every parser must:
1. Extend `BaseParser`
2. Set `format_name`, `file_extensions`, and optionally `implemented = False` for stubs
3. Implement `parse(filepath) -> ParseResult` — **never raise**; capture all errors in `ParseDiagnostics`
4. Populate `ParseDiagnostics` with format confidence, stream coverage, warnings, and errors
5. Populate `Provenance` with parser_name, parser_version, engine_version, flight_duration_sec

## Example Structure

```python
from goose.parsers.base import BaseParser
from goose.parsers.diagnostics import ParseDiagnostics, ParseResult, StreamCoverage
from goose.forensics.models import Provenance
from goose import __version__ as _engine_version

class MyFormatParser(BaseParser):
    format_name = "myformat"
    file_extensions = [".myfmt"]
    VERSION = "1.0.0"

    def parse(self, filepath) -> ParseResult:
        filepath = Path(filepath)
        diag = ParseDiagnostics(
            parser_selected="MyFormatParser",
            detected_format="myformat",
            supported=True,
        )

        try:
            # ... parse the file ...
            flight = Flight(...)

            # Record stream coverage
            diag.stream_coverage = [
                StreamCoverage("position", present=True, row_count=len(position_df)),
                StreamCoverage("battery", present=battery_df is not None, row_count=...),
                # ... etc for all 20 standard streams
            ]

            # Compute parser confidence
            diag.parser_confidence = self._compute_confidence(diag)

            prov = Provenance(
                parser_name="MyFormatParser",
                parser_version=self.VERSION,
                engine_version=_engine_version,
                source_file=str(filepath),
                flight_duration_sec=flight.metadata.duration_sec,
            )

            return ParseResult.success(flight=flight, diagnostics=diag, provenance=prov)

        except Exception as exc:
            diag.errors.append(str(exc))
            diag.success = False
            return ParseResult.failure(diag)
```

## Standard Streams

The 20 standard streams that plugins expect (listed in order of forensic importance):

| Stream | Flight field | Required by |
|--------|-------------|------------|
| `position` | `flight.position` | crash_detection, position_tracking |
| `battery` | `flight.battery` | battery_sag, payload_change_detection |
| `attitude` | `flight.attitude` | crash_detection, attitude_tracking |
| `attitude_setpoint` | `flight.attitude_setpoint` | crash_detection, attitude_tracking |
| `vibration` | `flight.vibration` | vibration |
| `gps` | `flight.gps` | gps_health |
| `motors` | `flight.motors` | motor_saturation |
| `ekf` | `flight.ekf` | ekf_consistency |
| `rc_input` | `flight.rc_input` | rc_signal |
| `velocity` | `flight.velocity` | position_tracking |
| `flight_mode` | `flight.mode_changes` | failsafe_events |
| `meta` | `flight.metadata` | log_health |

For streams that are absent in your format, record `StreamCoverage(stream_name, present=False)`.

## ParseDiagnostics.confidence_scope

Always set `confidence_scope = "parser_parse_quality"`. This is not analysis confidence or root-cause confidence — it purely reflects how complete and reliable the parse was.

## Registration

After implementing, add your parser to `src/goose/parsers/detect.py:_ALL_PARSERS`.

## Writing Tests

Create `tests/test_parsers/test_myformat_parser.py` with:
1. A fixture file in `tests/fixtures/` (real or synthetic)
2. A test that calls `parser.parse(fixture_path)` and checks `result.success`
3. A test that verifies the `ParseResult` contract: `result.flight` is not None, `result.diagnostics.parser_confidence` is set, stream coverage is populated
4. A test on a malformed file that verifies `parse()` does not raise and returns `ParseResult.failure()`

See `tests/test_parsers/test_ulog_parser.py` for examples.

## Provenance

`Provenance.source_evidence_id` is attached by the calling code (`analysis.py`) after the parse completes. You do not need to set it in the parser.
