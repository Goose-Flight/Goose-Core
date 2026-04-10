# Getting Started

Get up and running with Goose in under five minutes. Goose is a **local-first
flight forensic and investigation platform for UAV logs** — it parses flight
logs, runs diagnostic plugins, organizes results in auditable forensic cases,
and supports a fast session-only triage flow for one-off questions.

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

## Launch the Web GUI (recommended)

The web GUI is the primary product surface. Launch it with:

```bash
goose serve
```

Open `http://localhost:8000` in your browser.

### The welcome screen

On first launch you are offered two entry paths and a profile selector:

- **Quick Analysis** — drag a log in, get findings, hypotheses, and a summary.
  Session-only; nothing is persisted. Ideal for a one-off "what happened?"
  question. You can promote any Quick Analysis run to a full Investigation
  Case with one click.
- **Investigation Case** — case-oriented workflow with evidence ingest,
  SHA-256/SHA-512 hashing, chain of custody, append-only audit log, and
  saved analysis runs. Built for deeper work you want to keep or share.
- **Open Recent Case** — jump straight back into a previously created case.

### Profile selector

At the top of the welcome screen you pick a **profile** that tailors defaults
and wording for your role:

- **Racer** — FPV racers and performance tuners
- **Research / University** — research labs and academic flight test
- **Shop / Repair** — drone repair shops and triage
- **Factory / QA** — manufacturing acceptance testing
- **Gov / Mil** — public safety and mission operators
- **Advanced** — power users who want full control
- **Default** — balanced defaults for general use

Profiles only change which plugins are emphasized, which charts appear first,
which case metadata fields are prominent, and which wording the reports use
("Run" vs "Case" vs "Sortie" vs "Test"). The underlying forensic artifact is
identical across profiles — same parser, same plugins, same canonical models.
You can change profiles at any time.

## CLI crash analysis

You can also point Goose at a PX4 ULog file directly from the command line:

```bash
goose crash flight.ulg
```

Goose parses the log, runs every applicable analysis plugin, and prints a
crash report:

```
🪿 Goose v1.3.4 — Crash Analysis

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
