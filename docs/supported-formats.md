# Supported Formats

Goose supports **PX4 ULog, ArduPilot DataFlash, and generic CSV** natively.
A stub parser exists for MAVLink TLog in Core; the real TLog parser ships in Goose Pro.

## Format summary

| Format | Extensions | Autopilot | Status |
| --- | --- | --- | --- |
| PX4 ULog | `.ulg` | PX4 | **Fully supported** |
| ArduPilot DataFlash | `.bin`, `.log` | ArduPilot | **Supported** (basic message extraction) |
| MAVLink telemetry | `.tlog` | Any MAVLink | Core stub only — real parser in Goose Pro |
| Generic CSV | `.csv` | Any | **Supported** (stream heuristics) |

---

## PX4 ULog (.ulg)

**Status: Fully supported**

ULog is the native binary log format used by PX4 autopilots. Goose uses the
[pyulog](https://github.com/PX4/pyulog) library to parse these files.

### Where to find ULog files

- **SD card** — PX4 writes logs to the SD card under `/log/` as `.ulg` files.
- **QGroundControl** — download logs via the Log Download page in QGC.
- **PX4 Flight Review** — public logs are available at
  [review.px4.io](https://review.px4.io).

### What Goose extracts

The ULog parser extracts the following data from PX4 topics:

| Data | PX4 Topics |
| --- | --- |
| Position | `vehicle_global_position`, `vehicle_local_position` |
| Position setpoint | `vehicle_local_position_setpoint`, `position_setpoint_triplet` |
| Velocity | `vehicle_local_position` (vx, vy, vz) |
| Attitude | `vehicle_attitude` (quaternion, converted to roll/pitch/yaw) |
| Attitude setpoint | `vehicle_attitude_setpoint` |
| Angular rates | `vehicle_angular_velocity` |
| Rate setpoint | `vehicle_rates_setpoint` |
| Battery | `battery_status` (voltage, current, remaining) |
| GPS | `vehicle_gps_position`, `sensor_gps` |
| Motors | `actuator_outputs`, `actuator_motors` (normalized 0-1) |
| Vibration | `sensor_combined`, `sensor_accel` |
| RC input | `input_rc` (RSSI, channel values) |
| EKF | `estimator_status`, `estimator_sensor_bias` |
| CPU load | `cpuload` |
| Mode changes | `vehicle_status` (nav_state / main_state transitions) |
| Events | ULog logged messages |
| Parameters | ULog initial and changed parameters |

### Flight mode mapping

Goose maps PX4 navigation state integers to human-readable mode names:

| State | Mode |
| --- | --- |
| 0 | Manual |
| 1 | Altitude |
| 2 | Position |
| 3 | Mission |
| 4 | Hold |
| 5 | Return |
| 6 | Acro |
| 7 | Offboard |
| 8 | Stabilized |
| 9 | Rattitude |
| 10 | Takeoff |
| 11 | Land |
| 12 | Follow Target |
| 13 | Precision Land |
| 14 | Orbit |

---

## ArduPilot DataFlash (.bin, .log)

**Status: Supported (basic message extraction)**

DataFlash is the binary log format used by ArduPilot (Copter, Plane, Rover).
`.bin` files are the raw binary format; `.log` files are the text-decoded
equivalent.

Goose ships a real DataFlash parser (`implemented=True`) that performs basic
ArduPilot log parsing and message extraction. It returns a full `ParseResult`
with diagnostics. Coverage is at the foundational level — not all ArduPilot
topics are extracted. See the parser source for the current stream coverage.

---

## MAVLink Telemetry (.tlog)

**Status: Core stub only — real parser in Goose Pro**

MAVLink `.tlog` files record timestamped MAVLink messages as received by a
ground station (QGroundControl, Mission Planner, MAVProxy). They contain
telemetry from any MAVLink-compatible autopilot.

A stub parser exists in Core (`implemented=False`) that correctly identifies
the format and returns a structured unsupported-format diagnostic. A real TLog
parser — with MAVLink binary framing, HEARTBEAT/ATTITUDE/GPS/BATTERY_STATUS
extraction — is available as part of Goose Pro.

---

## Generic CSV (.csv)

**Status: Supported (stream heuristics)**

CSV support allows Goose to analyze exported telemetry from any source. The
parser uses heuristic column mapping to identify common telemetry fields
(timestamp, position, battery, attitude) regardless of the exact header names.

Goose ships a real CSV parser (`implemented=True`) that performs stream
heuristic detection and returns a full `ParseResult` with diagnostics. Coverage
depends on the columns present in the file. Standard naming conventions
(e.g., QGroundControl CSV export) will yield the best stream coverage.

---

## Format detection

Goose provides a detection module (`parse_file()`, `detect_parser()`,
`supported_formats()`) that selects the appropriate parser based on file
extension and content probing. Three parsers are functional in Core:

- `.ulg` — ULog parser (full PX4 topic extraction, full `ParseResult`)
- `.bin`, `.log` — DataFlash parser (basic ArduPilot message extraction)
- `.csv` — CSV parser (heuristic column mapping)
- `.tlog` — Core stub returns a structured unsupported-format diagnostic; real parser in Goose Pro

The parser framework uses the `ParseResult` contract, which returns
`(Flight | None, ParseDiagnostics, Provenance)` for every parse attempt.
The parse never raises -- it always returns structured diagnostic output,
even on failure.
