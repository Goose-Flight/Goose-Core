# Getting Started

Get up and running with Goose in under five minutes.
Goose reads your drone flight log and tells you what went wrong.

## Requirements

- Python 3.10 or newer

## Install

```bash
pip install goose-flight
```

Verify the installation:

```bash
goose doctor
```

This checks that all dependencies are importable and plugins are discovered.
If anything is missing, run `goose doctor --fix` to attempt automatic repair.

## Your first crash analysis

Point Goose at a PX4 ULog file:

```bash
goose crash flight.ulg
```

Goose parses the log, runs every applicable analysis plugin, and prints a
crash report:

```
🪿 Goose v1.0.0 — Crash Analysis

  File: flight.ulg
  Aircraft: PX4 1.14.0 · Multirotor · Pixhawk 6C
  Duration: 4m32s · Mode: Position

  🔴 CRASH DETECTED — Motor Failure (87% confidence)

  Root cause: Motor 3 output dropped to zero at t=261s while
  remaining motors were active, consistent with ESC or motor failure.

  Timeline:
    t=258s  Motor 3 output dropped below threshold
    t=259s  Attitude divergence exceeded 30 deg
    t=261s  Descent rate exceeded 5 m/s
    t=262s  High-g impact detected (4.2 g)

  Plugin Results:
  ✗ crash_detection ....   0   Crash detected: motor failure
  ✗ vibration ..........  25   High vibration with clipping detected
  ✓ battery_sag ........  95   Battery voltage nominal

  Inspect:
  ☐ Check motor 3 bearings and shaft play
  ☐ Inspect ESC solder joints and capacitors
  ☐ Check wiring harness for chafing or loose connectors
  ☐ Inspect propeller for cracks or deformation

  Overall Score: 18/100
```

### What the output means

- **Crash confidence** — how certain Goose is that a crash occurred (0-100%).
  Values above 70% are high confidence.
- **Root cause** — a one-line explanation of the most likely failure.
- **Timeline** — key events leading to the crash, ordered by time.
- **Plugin Results** — each plugin scores the flight from 0 (critical failure)
  to 100 (no issues). Worst scores appear first.
- **Inspect** — physical checklist items to verify on the aircraft.
- **Overall Score** — weighted average across all plugins (0-100).

## Save the report to a file

```bash
goose crash flight.ulg -o report.txt
```

Or export as JSON for programmatic use:

```bash
goose crash flight.ulg -f json -o report.json
```

## Run a full analysis (all plugins)

The `analyze` command runs every plugin individually without synthesizing a
crash root cause. Useful for pre-flight validation or health checks:

```bash
goose analyze flight.ulg
```

Run only specific plugins:

```bash
goose analyze flight.ulg --plugin vibration --plugin crash_detection
```

## List installed plugins

```bash
goose plugins list
```

## Check the version

```bash
goose --version
```

## Where to get log files

PX4 logs are stored on the SD card in `/log/` as `.ulg` files. You can also
download logs from [PX4 Flight Review](https://review.px4.io) or pull them
from QGroundControl's log download feature.

## Next steps

- [CLI Reference](cli-reference.md) — full command and option documentation
- [Supported Formats](supported-formats.md) — which log formats Goose can read
- [Writing Plugins](writing-plugins.md) — extend Goose with your own checks
- [Configuration](configuration.md) — customize thresholds and output settings
