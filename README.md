# Goose — Drone Flight Crash Analysis

Open source drone flight log analysis and crash diagnosis.
Point it at a log file, get answers in 10 seconds.

## Install

```bash
pip install goose-flight
```

## Analyze a crash

```bash
goose crash flight.ulg
```

## Full validation

```bash
goose analyze flight.ulg
```

## Web dashboard

```bash
goose serve
```

## Supported formats

- PX4 ULog (.ulg)
- ArduPilot DataFlash (.bin, .log)
- MAVLink telemetry (.tlog)
- Generic CSV (.csv)

## Features

- Automated crash root cause diagnosis with confidence scoring
- 11 built-in analysis plugins (vibration, battery, GPS, motors, EKF, and more)
- Professional PDF/HTML validation reports
- Local web UI with flight map, telemetry charts, and findings table
- Plugin architecture — extend with your own checks
- Air-gapped — works with zero internet
- Cross-platform — Linux, macOS, Windows, Raspberry Pi

## Writing plugins

See [docs/writing-plugins.md](docs/writing-plugins.md)

## License

Apache 2.0
