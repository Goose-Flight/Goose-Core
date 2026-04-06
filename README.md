```
   _____
  / ___ \
 / /   \ \   GOOSE
| |     | |  Drone Flight Log Crash Analysis Engine
| |     | |
 \ \___/ /   "Point it at a log. Get answers."
  \_____/
```

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](https://github.com/Goose-Flight/Goose-Core/releases)

---

Goose is an open-source, air-gapped drone flight log analysis and crash diagnosis engine. It parses PX4 ULog files, runs a suite of diagnostic plugins, and tells you why your drone crashed — in under 10 seconds, with no internet required.

Think of it as Snort for drone flight data.

---

## Quick Start

```bash
pip install goose-flight
goose analyze flight.ulg
goose serve
```

That's it. You now have a full crash report and a local web dashboard.

---

## What It Does

Goose takes a flight log, runs it through a plugin engine, and produces structured findings with confidence scores. You can view results in the terminal or through a local web dashboard at `localhost:8000`.

```
goose crash flight.ulg       # identify the most likely crash cause
goose analyze flight.ulg     # full validation across all plugins
goose serve                  # launch the web dashboard
goose doctor                 # verify your installation
goose plugins list           # list installed plugins
```

No data leaves your machine. No account required. Works on Linux, macOS, Windows, and Raspberry Pi.

---

## Plugins

Goose v1.0 ships with 5 analysis plugins:

| Plugin              | What It Checks                                                   |
|---------------------|------------------------------------------------------------------|
| `crash_detection`   | Identifies crash events, type (hard/soft), and timestamp        |
| `vibration`         | IMU vibration levels, clipping, and resonance patterns          |
| `battery_sag`       | Voltage sag under load, cell imbalance, brownout risk           |
| `gps_health`        | Fix quality, satellite count, HDOP, and position drift          |
| `motor_saturation`  | Motor output saturation, asymmetry, and control authority loss  |

Each plugin emits findings with a severity level (`info`, `warning`, `critical`) and a confidence score.

Six additional plugins are planned for v1.1 — see the [Roadmap](#roadmap).

---

## Web Dashboard

```bash
goose serve
```

Opens a local web UI at `http://localhost:8000`. The dashboard includes:

- Flight timeline with crash event markers
- Telemetry charts (altitude, attitude, battery, GPS)
- Plugin findings table with severity and confidence
- Raw log browser

The dashboard is fully local. No telemetry is sent anywhere.

---

## CLI Reference

```bash
# Crash diagnosis — most likely root cause with confidence score
goose crash flight.ulg

# Full validation — all plugins, all findings
goose analyze flight.ulg

# Launch the web dashboard
goose serve

# Check that all dependencies are installed and working
goose doctor

# List installed plugins
goose plugins list

# Run a specific plugin only
goose analyze flight.ulg --plugin vibration

# Output as JSON
goose analyze flight.ulg --format json

# Verbose output
goose analyze flight.ulg --verbose
```

---

## Architecture

```
Log File (.ulg)
     |
     v
  [ Parser ]
     |
     v
 [ Flight Object ]          <-- structured, format-agnostic representation
     |
     v
 [ Plugin Engine ]
  |    |    |    |    |
  v    v    v    v    v
 crash vib  bat  gps  motor
     |
     v
 [ Findings ]
  |            |
  v            v
[ CLI Report ] [ Web Dashboard ]
```

Parsers are format-specific adapters. Currently only the PX4 ULog parser is implemented. The plugin engine is parser-agnostic — plugins operate on the Flight object, not the raw log format.

---

## Plugin System

Goose uses Python entry points for plugin discovery. Any package can register a Goose plugin:

```python
# In your plugin package's pyproject.toml
[project.entry-points."goose.plugins"]
my_check = "my_package.plugin:MyPlugin"
```

```python
# my_package/plugin.py
from goose.plugin import BasePlugin, Finding, Severity

class MyPlugin(BasePlugin):
    name = "my_check"
    description = "Checks something important"

    def run(self, flight) -> list[Finding]:
        findings = []
        # inspect flight.imu, flight.gps, flight.battery, etc.
        if some_condition:
            findings.append(Finding(
                severity=Severity.WARNING,
                message="Something looks off",
                confidence=0.85,
            ))
        return findings
```

Install your plugin and it will appear automatically:

```bash
pip install goose-plugin-my-check
goose plugins list
```

See [docs/writing-plugins.md](docs/writing-plugins.md) for the full API reference.

---

## Supported Formats

| Format                  | Status      |
|-------------------------|-------------|
| PX4 ULog (`.ulg`)       | Supported   |
| ArduPilot DataFlash (`.bin`, `.log`) | Planned (v1.1) |
| MAVLink telemetry (`.tlog`) | Planned (v1.1) |
| Generic CSV (`.csv`)    | Planned (v1.1) |

---

## Roadmap

### v1.0 (current)

- [x] PX4 ULog parser
- [x] 5 analysis plugins: crash_detection, vibration, battery_sag, gps_health, motor_saturation
- [x] CLI with crash diagnosis and full validation modes
- [x] Local web dashboard
- [x] Plugin system via Python entry points
- [x] Air-gapped operation

### v1.1 (planned)

| Item                        | Description                                      |
|-----------------------------|--------------------------------------------------|
| 6 additional plugins        | EKF health, wind estimation, RC signal, compass, airspeed, attitude control |
| ArduPilot DataFlash parser  | Support for `.bin` and `.log` files              |
| PDF reports                 | Exportable crash reports with charts             |
| MAVLink tlog support        | Ground control station telemetry logs            |
| CSV import                  | Generic tabular log data                         |
| Batch processing            | Analyze multiple logs in one command             |

---

## Contributing

Contributions are welcome — bug reports, new plugins, parser implementations, and documentation improvements.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing requirements, and the PR process.

---

## License

Apache 2.0. See [LICENSE](LICENSE).
