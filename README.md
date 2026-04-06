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

## Documentation

- **[Getting Started](docs/getting-started.md)** — Installation and your first crash analysis
- **[CLI Reference](docs/cli-reference.md)** — Complete command documentation
- **[FAQ](docs/faq.md)** — Common questions about installation, usage, compatibility
- **[Troubleshooting](docs/troubleshooting.md)** — Solutions for common issues
- **[API Reference](docs/api-reference.md)** — REST API for programmatic integration
- **[Advanced Usage](docs/advanced-usage.md)** — Batch processing, automation, custom integrations
- **[Writing Plugins](docs/writing-plugins.md)** — Extend Goose with custom analysis checks
- **[Configuration](docs/configuration.md)** — Customize thresholds and behavior
- **[Supported Formats](docs/supported-formats.md)** — Log file format details
- **[Crash Analysis Guide](docs/crash-analysis-guide.md)** — Understanding crash reports

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and PR process.

## License

Apache 2.0
