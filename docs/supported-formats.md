# Supported Formats

Goose reads flight logs from several autopilot systems. This page lists each
format, its file extensions, and current support status.

## Format summary

| Format | Extensions | Autopilot | Status |
| --- | --- | --- | --- |
| PX4 ULog | `.ulg` | PX4 | **Fully supported** |
| ArduPilot DataFlash | `.bin`, `.log` | ArduPilot | Planned |
| MAVLink telemetry | `.tlog` | Any MAVLink | Planned |
| Generic CSV | `.csv` | Any | Planned |

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

**Status: Planned**

DataFlash is the binary log format used by ArduPilot (Copter, Plane, Rover).
`.bin` files are the raw binary format; `.log` files are the text-decoded
equivalent.

Parser support is planned for a future release.

---

## MAVLink Telemetry (.tlog)

**Status: Planned**

MAVLink `.tlog` files record timestamped MAVLink messages as received by a
ground station (QGroundControl, Mission Planner, MAVProxy). They contain
telemetry from any MAVLink-compatible autopilot.

Parser support is planned for a future release. The `pymavlink` library is
already included as a dependency.

---

## Generic CSV (.csv)

**Status: Planned**

CSV support will allow Goose to analyze exported telemetry from any source,
provided the columns follow a documented naming convention.

Parser support is planned for a future release.

---

## Format detection

Goose currently selects the parser based on file extension:

- `.ulg` — ULog parser
- All other extensions — not yet supported (produces an error)

Automatic format detection by file content is planned for a future release.
