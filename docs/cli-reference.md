# CLI Reference

Goose provides five commands. Run `goose --help` for a summary or
`goose <command> --help` for details on any command.

## Global options

| Option | Description |
| --- | --- |
| `--version` | Print the Goose version and exit |
| `--help` | Show help and exit |

---

## goose crash

Analyze a flight log for crash root cause. Parses the log, runs all
applicable plugins, synthesizes findings into a root cause diagnosis with
confidence scoring, and prints (or saves) the report.

```
goose crash [OPTIONS] LOGFILE
```

### Arguments

| Argument | Description |
| --- | --- |
| `LOGFILE` | Path to a flight log file (must exist, cannot be a directory) |

### Options

| Option | Short | Default | Description |
| --- | --- | --- | --- |
| `--output PATH` | `-o` | — | Save the report to a file |
| `--format FORMAT` | `-f` | `text` | Output format: `text` or `json` |
| `--verbose` | `-v` | off | Show detailed evidence for each finding |
| `--no-color` | — | off | Disable colored terminal output |

### Text output

The text report includes:

- **Header** — Goose version, file name, aircraft info (autopilot, firmware,
  vehicle type, hardware), flight duration, and primary mode.
- **Crash verdict** — `CRASH DETECTED` (red) with classification and
  confidence percentage, or `NO CRASH DETECTED` (green).
- **Root cause** — one-line explanation of the most likely failure.
- **Timeline** — chronological list of key events (`t=Xs  description`).
- **Plugin Results** — table showing each plugin's score (0-100) and summary.
  Icons: `✓` (90+), `⚠` (60-89), `✗` (below 60).
- **Inspect** — physical checklist items to verify on the aircraft.
- **Overall Score** — weighted average across all plugins.

### JSON output

When `--format json` is used, the output is a JSON object with these fields:

| Field | Type | Description |
| --- | --- | --- |
| `version` | string | Goose version |
| `file` | string | Source log file path |
| `autopilot` | string | Detected autopilot (`px4`) |
| `firmware_version` | string | Firmware version string |
| `vehicle_type` | string | Vehicle type (e.g., `multirotor`) |
| `duration_sec` | number | Flight duration in seconds |
| `crashed` | boolean | Whether a crash was detected |
| `crash_classification` | string | Classification (see below) |
| `crash_confidence` | number | Confidence 0.0 - 1.0 |
| `root_cause` | string | Root cause description |
| `evidence_chain` | array | List of evidence strings |
| `contributing_factors` | array | List of contributing factor strings |
| `inspect_checklist` | array | Physical inspection items |
| `timeline` | array | Objects with `timestamp`, `event`, `severity` |
| `findings` | array | Per-plugin findings (see below) |
| `overall_score` | number | Weighted overall score 0-100 |

Each entry in `findings`:

| Field | Type | Description |
| --- | --- | --- |
| `plugin` | string | Plugin name |
| `title` | string | Finding title |
| `severity` | string | `critical`, `warning`, `info`, or `pass` |
| `score` | number | Score 0-100 |
| `description` | string | Detailed description |

### Crash classifications

| Classification | Description |
| --- | --- |
| `motor_failure` | A motor or ESC stopped responding |
| `power_loss` | Battery or power system failure |
| `gps_loss` | GPS signal lost during GPS-dependent mode |
| `pilot_error` | Control input led to unrecoverable state |
| `mechanical` | Structural or mechanical failure detected |
| `unknown` | Crash detected but cause could not be determined |

### Examples

```bash
# Basic crash analysis
goose crash flight.ulg

# Save JSON report
goose crash flight.ulg -f json -o crash_report.json

# Verbose text output with all evidence
goose crash flight.ulg -v

# Pipe JSON to another tool
goose crash flight.ulg -f json | jq '.root_cause'
```

---

## goose analyze

Run all analysis plugins against a flight log and report each finding
individually. Unlike `crash`, this command does not synthesize a root cause —
it shows raw plugin output for detailed inspection.

```
goose analyze [OPTIONS] LOGFILE
```

### Arguments

| Argument | Description |
| --- | --- |
| `LOGFILE` | Path to a flight log file |

### Options

| Option | Short | Default | Description |
| --- | --- | --- | --- |
| `--output PATH` | `-o` | — | Save the report to a file |
| `--format FORMAT` | `-f` | `text` | Output format: `text` or `json` |
| `--verbose` | `-v` | off | Show description and evidence per finding |
| `--plugin NAME` | — | all | Run only the named plugin (repeatable) |
| `--no-color` | — | off | Disable colored terminal output |

### JSON output

| Field | Type | Description |
| --- | --- | --- |
| `version` | string | Goose version |
| `file` | string | Source log file path |
| `plugins_run` | array | Names of plugins that were executed |
| `findings` | array | Per-finding objects (same schema as `crash`) |

### Examples

```bash
# Full analysis
goose analyze flight.ulg

# Run only vibration and crash detection plugins
goose analyze flight.ulg --plugin vibration --plugin crash_detection

# Verbose JSON output
goose analyze flight.ulg -f json -v -o analysis.json
```

---

## goose serve

Start the Goose web server. Launches a uvicorn server hosting the FastAPI
application with the web GUI.

> **Note:** The web GUI is the primary product surface. It provides
> case-oriented workflow: case creation, evidence upload, analysis, findings
> view, audit trail, and parse diagnostics.

```
goose serve [OPTIONS]
```

### Options

| Option | Short | Default | Description |
| --- | --- | --- | --- |
| `--host TEXT` | `-h` | `127.0.0.1` | Bind address |
| `--port INT` | `-p` | `8000` | Bind port |
| `--reload` | — | off | Enable auto-reload (development mode) |

### Examples

```bash
# Start on default address
goose serve

# Bind to all interfaces on port 9000
goose serve -h 0.0.0.0 -p 9000

# Development mode with auto-reload
goose serve --reload
```

---

## goose doctor

Verify that Goose and all its dependencies are properly installed. Checks
core Python packages, plugin discovery, and parser availability.

```
goose doctor [OPTIONS]
```

### Options

| Option | Default | Description |
| --- | --- | --- |
| `--fix` | off | Attempt to `pip install` missing packages |

### What it checks

1. **Dependencies** — imports each required package (click, pandas, numpy,
   pyulog, pymavlink, fastapi, uvicorn, jinja2, yaml, rich) and reports
   version or failure.
2. **Plugins** — discovers all registered plugins via entry points.
3. **Parsers** — verifies the ULog parser is importable.

Exits with code 1 if any issues are found.

### Examples

```bash
# Check installation health
goose doctor

# Auto-fix missing packages
goose doctor --fix
```

---

## goose plugins

Manage and inspect analysis plugins.

### goose plugins list

List all installed analysis plugins in a table.

```
goose plugins list [--json]
```

| Option | Description |
| --- | --- |
| `--json` | Output as a JSON array |

Each plugin entry shows: name, version, minimum flight mode, and description.

### goose plugins info

Show details about a specific plugin.

```
goose plugins info NAME
```

| Argument | Description |
| --- | --- |
| `NAME` | Plugin name (e.g., `vibration`, `crash_detection`) |

### Examples

```bash
# List all plugins
goose plugins list

# JSON output for scripting
goose plugins list --json

# Details for a specific plugin
goose plugins info vibration
```
