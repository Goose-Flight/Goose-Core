# PX4 Flight Log Analysis — Reference Document

**Purpose:** Comprehensive reference for plugin developers in Goose-Core. Covers the ULog file
format, uORB message catalogue, PX4-recommended analysis techniques, failure mode signatures,
filter tuning, and the third-party tooling landscape. All thresholds are drawn from official PX4
documentation and community analysis practice.

---

## Table of Contents

1. [ULog File Format](#1-ulog-file-format)
2. [uORB Topic Catalogue](#2-uorb-topic-catalogue)
3. [Flight Log Analysis Methodology](#3-flight-log-analysis-methodology)
4. [Failure Mode Signatures](#4-failure-mode-signatures)
5. [Filter Tuning and Vibration Analysis](#5-filter-tuning-and-vibration-analysis)
6. [EKF Health and Innovation Monitoring](#6-ekf-health-and-innovation-monitoring)
7. [GPS and Position Estimation](#7-gps-and-position-estimation)
8. [Battery and Power Analysis](#8-battery-and-power-analysis)
9. [Motor and Actuator Analysis](#9-motor-and-actuator-analysis)
10. [RC and Failsafe Analysis](#10-rc-and-failsafe-analysis)
11. [Analysis Tools](#11-analysis-tools)
12. [Gaps in Current Goose Plugins](#12-gaps-in-current-goose-plugins)

---

## 1. ULog File Format

### Overview

ULog is PX4's native binary flight log format. Files use the `.ulg` extension and are written
directly by the flight controller in real time. The format is documented at:
`https://docs.px4.io/main/en/dev_log/ulog_file_format`

### File Structure

A ULog file has three sections in strict order:

```
[File Header]        — magic, version, timestamp
[Definition Section] — message formats, subscriptions, parameters, info
[Data Section]       — logged data messages interleaved with metadata
```

### File Header (16 bytes)

| Offset | Size | Type   | Description                              |
|--------|------|--------|------------------------------------------|
| 0      | 7    | char[] | Magic: `ULog\x01\x12\x35`               |
| 7      | 1    | uint8  | File version (currently `1`)             |
| 8      | 8    | uint64 | Timestamp at log start (microseconds)    |

### Message Types

Every message in the definition and data sections begins with a 3-byte header:

```
uint16  msg_size   — size of message body in bytes (not including header)
uint8   msg_type   — single-character type identifier
```

#### Definition Section Message Types

| Type Char | Name                  | Purpose                                         |
|-----------|-----------------------|-------------------------------------------------|
| `F`       | FlagBits              | Compatibility flags (appended data flag, etc.)  |
| `B`       | FlagBits              | (same as F, alternate)                          |
| `I`       | Information           | Key-value metadata string (e.g. `ver_sw`)       |
| `M`       | InformationMultiple   | Array of key-value metadata                     |
| `P`       | Parameter             | Initial parameter value (name + value)          |
| `Q`       | ParameterDefault      | Parameter default value (name + value)          |
| `A`       | AddLoggedMessage      | Subscription: topic name + multi_id + msg_id    |
| `R`       | RemoveLoggedMessage   | Unsubscription by msg_id                        |
| `F`       | Format                | Message format definition (struct schema)       |

#### Data Section Message Types

| Type Char | Name            | Purpose                                               |
|-----------|-----------------|-------------------------------------------------------|
| `D`       | Data            | Logged data sample for a subscribed topic             |
| `L`       | LoggedString    | Text message with log level and timestamp             |
| `C`       | TaggedLoggedString | Text message with tag field                        |
| `S`       | Synchronization | Sync marker for recovery after corruption             |
| `O`       | Dropout         | Marks a dropout (data gap) with duration in ms        |
| `P`       | Parameter       | Parameter value change mid-flight                     |
| `Q`       | ParameterDefault| Parameter default change mid-flight                   |

### Format Messages (`F` type)

Define the binary layout of each uORB message. Format:

```
message_name:field1_type field1_name;field2_type field2_name;...
```

Supported types: `int8_t`, `uint8_t`, `int16_t`, `uint16_t`, `int32_t`, `uint32_t`,
`int64_t`, `uint64_t`, `float`, `double`, `bool`, `char`. Arrays use `type[N]` notation.

Every message has an implicit `uint64_t timestamp` field (microseconds since boot).

### Logged String (`L` type) — Log Levels

| Value | Syslog Level  | Meaning                     |
|-------|---------------|-----------------------------|
| 0     | EMERGENCY     | System unusable             |
| 1     | ALERT         | Action must be taken immediately |
| 2     | CRITICAL      | Critical conditions         |
| 3     | ERROR         | Error conditions            |
| 4     | WARNING       | Warning conditions          |
| 5     | NOTICE        | Normal but significant      |
| 6     | INFO          | Informational               |
| 7     | DEBUG         | Debug messages              |

### Information Fields (common `ver_sw` etc.)

Standard keys found in `I` (Information) messages:

| Key              | Type   | Description                                       |
|------------------|--------|---------------------------------------------------|
| `ver_sw`         | string | Firmware git hash or version string               |
| `ver_hw`         | string | Hardware identifier (e.g. `PX4FMU_V5X`)           |
| `sys_name`       | string | System name                                       |
| `time_ref_utc`   | uint64 | UTC time reference in microseconds                |
| `replay`         | string | If present, log was generated from replay         |
| `boot_console`   | string | Console output at boot                            |

### pyulog Usage (Python)

The `pyulog` library is the standard way to read ULog files in Python:

```python
from pyulog import ULog

ulog = ULog("flight.ulg")

# Access metadata
print(ulog.start_timestamp)      # microseconds
print(ulog.last_timestamp)       # microseconds
print(ulog.initial_parameters)   # dict[str, float]
print(ulog.msg_info_dict)        # dict of Info messages
print(ulog.logged_messages)      # list of LoggedMessages

# Access topic data
for dataset in ulog.data_list:
    print(dataset.name, list(dataset.data.keys()))
    # dataset.data is dict[field_name, numpy_array]
```

---

## 2. uORB Topic Catalogue

This section documents the uORB topics most relevant to flight analysis, their fields, units,
and significance. All timestamps are `uint64_t` in microseconds since boot.

### 2.1 Sensor Data

#### `sensor_combined`

Fused IMU data (primary topic for vibration analysis).

| Field                        | Type      | Units  | Description                       |
|------------------------------|-----------|--------|-----------------------------------|
| `timestamp`                  | uint64_t  | µs     | Sample time                       |
| `accelerometer_m_s2[3]`      | float[3]  | m/s²   | Accelerometer X, Y, Z             |
| `accelerometer_integral_dt`  | uint32_t  | µs     | Integration delta time            |
| `accelerometer_clipping`     | uint8_t   | —      | Clipping bitmask (per axis)       |
| `gyro_rad[3]`                | float[3]  | rad/s  | Gyroscope X, Y, Z                 |
| `gyro_integral_dt`           | uint32_t  | µs     | Gyro integration delta time       |

**Analysis use:** Primary source for vibration RMS, clipping detection, and IMU health.

#### `sensor_accel` (newer PX4 versions)

Raw accelerometer data per IMU instance. Multi-instance topic (multi_id distinguishes IMUs).

| Field    | Type     | Units  | Description        |
|----------|----------|--------|--------------------|
| `x`      | float    | m/s²   | Acceleration X     |
| `y`      | float    | m/s²   | Acceleration Y     |
| `z`      | float    | m/s²   | Acceleration Z     |
| `temperature` | float | °C   | Sensor temperature |

#### `sensor_gyro` (newer PX4 versions)

Raw gyroscope data per IMU instance.

| Field    | Type  | Units  | Description          |
|----------|-------|--------|----------------------|
| `x`      | float | rad/s  | Angular rate X       |
| `y`      | float | rad/s  | Angular rate Y       |
| `z`      | float | rad/s  | Angular rate Z       |
| `temperature` | float | °C | Sensor temperature  |

#### `sensor_baro`

Barometer data.

| Field         | Type  | Units | Description             |
|---------------|-------|-------|-------------------------|
| `pressure`    | float | hPa   | Static pressure         |
| `temperature` | float | °C    | Sensor temperature      |
| `error_count` | uint64_t | — | Accumulated error count |

### 2.2 GPS / GNSS

#### `vehicle_gps_position` (legacy) / `sensor_gps` (newer)

Both topics have equivalent fields; `sensor_gps` is preferred in PX4 v1.13+.

| Field               | Type     | Units    | Description                                  |
|---------------------|----------|----------|----------------------------------------------|
| `lat`               | int32_t  | deg×1e7  | Latitude (divide by 1e7 for degrees)         |
| `lon`               | int32_t  | deg×1e7  | Longitude (divide by 1e7 for degrees)        |
| `alt`               | int32_t  | mm       | Altitude MSL (divide by 1000 for metres)     |
| `alt_ellipsoid`     | int32_t  | mm       | Altitude above WGS84 ellipsoid              |
| `s_variance_m_s`    | float    | m/s      | Speed accuracy estimate                      |
| `c_variance_rad`    | float    | rad      | Course accuracy estimate                     |
| `eph`               | float    | m        | Horizontal position accuracy (1σ)            |
| `epv`               | float    | m        | Vertical position accuracy (1σ)              |
| `hdop`              | float    | —        | Horizontal dilution of precision             |
| `vdop`              | float    | —        | Vertical dilution of precision               |
| `noise_per_ms`      | int32_t  | —        | GPS noise per millisecond                    |
| `jamming_indicator` | uint8_t  | —        | Anti-jamming indicator (0=OK, >0=jamming)    |
| `vel_m_s`           | float    | m/s      | GPS ground speed magnitude                   |
| `vel_n_m_s`         | float    | m/s      | North velocity component                     |
| `vel_e_m_s`         | float    | m/s      | East velocity component                      |
| `vel_d_m_s`         | float    | m/s      | Down velocity component                      |
| `cog_rad`           | float    | rad      | Course over ground                           |
| `timestamp_time_relative` | int32_t | µs | Time relative to `time_utc_usec`          |
| `time_utc_usec`     | uint64_t | µs       | Absolute UTC time (epoch microseconds)       |
| `satellites_used`   | uint8_t  | —        | Number of satellites used in fix             |
| `fix_type`          | uint8_t  | —        | 0=None, 1=No Fix, 2=2D, 3=3D, 4=DGPS, 5=RTK Float, 6=RTK Fixed |
| `spoofing_state`    | uint8_t  | —        | 0=Unknown, 1=No spoofing, 2=Possible, 3=Likely |

**Key thresholds:**
- `satellites_used`: minimum 6 for 3D fix, recommended ≥ 8 for reliable operation
- `eph` (horizontal accuracy): < 1.0 m excellent, < 2.5 m good, > 5.0 m poor
- `hdop`: < 1.0 excellent, < 2.0 good, > 2.5 poor, > 5.0 unacceptable
- `fix_type`: 3 (3D) is minimum for autonomous flight; 6 (RTK Fixed) is best

### 2.3 Position and Velocity Estimation

#### `vehicle_local_position`

EKF output: estimated position and velocity in local NED (North-East-Down) frame.

| Field          | Type  | Units | Description                                       |
|----------------|-------|-------|---------------------------------------------------|
| `x`            | float | m     | North position (from takeoff reference)           |
| `y`            | float | m     | East position                                     |
| `z`            | float | m     | Down position (negative = above ground)           |
| `vx`           | float | m/s   | North velocity                                    |
| `vy`           | float | m/s   | East velocity                                     |
| `vz`           | float | m/s   | Down velocity (positive = descending)             |
| `ax`           | float | m/s²  | North acceleration (EKF output)                   |
| `ay`           | float | m/s²  | East acceleration                                 |
| `az`           | float | m/s²  | Down acceleration                                 |
| `heading`      | float | rad   | Yaw heading                                       |
| `ref_lat`      | double| deg   | Reference latitude (origin of local frame)        |
| `ref_lon`      | double| deg   | Reference longitude                               |
| `ref_alt`      | float | m     | Reference altitude MSL                            |
| `dist_bottom`  | float | m     | Distance to ground (from rangefinder if available)|
| `xy_valid`     | bool  | —     | Horizontal position estimate valid                |
| `z_valid`      | bool  | —     | Vertical position estimate valid                  |
| `v_xy_valid`   | bool  | —     | Horizontal velocity estimate valid                |
| `v_z_valid`    | bool  | —     | Vertical velocity estimate valid                  |
| `xy_global`    | bool  | —     | True if position fused with GPS                   |
| `z_global`     | bool  | —     | True if altitude fused with global source         |

#### `vehicle_global_position`

EKF output: estimated position in global WGS84 frame.

| Field              | Type   | Units | Description                              |
|--------------------|--------|-------|------------------------------------------|
| `lat`              | double | deg   | Latitude                                 |
| `lon`              | double | deg   | Longitude                                |
| `alt`              | float  | m     | Altitude MSL                             |
| `alt_ellipsoid`    | float  | m     | Altitude above WGS84 ellipsoid          |
| `delta_alt`        | float  | m     | Recent altitude change                   |
| `eph`              | float  | m     | Estimated horizontal accuracy            |
| `epv`              | float  | m     | Estimated vertical accuracy              |
| `terrain_alt`      | float  | m     | Terrain altitude estimate                |
| `terrain_alt_valid`| bool   | —     | True if terrain altitude is valid        |
| `dead_reckoning`   | bool   | —     | True if position is dead-reckoned (no GPS)|

### 2.4 Attitude

#### `vehicle_attitude`

EKF output: estimated vehicle attitude as unit quaternion.

| Field       | Type     | Units | Description                                        |
|-------------|----------|-------|----------------------------------------------------|
| `q[4]`      | float[4] | —     | Unit quaternion [w, x, y, z] (Hamilton convention) |
| `delta_q_reset[4]` | float[4] | — | Quaternion delta since last reset              |
| `quat_reset_counter` | uint8_t | — | Counter incremented on each reset             |

**Euler angle conversion (per Goose parser):**
```python
roll  = atan2(2*(q0*q1 + q2*q3), 1 - 2*(q1² + q2²))
pitch = asin(clip(2*(q0*q2 - q3*q1), -1, 1))
yaw   = atan2(2*(q0*q3 + q1*q2), 1 - 2*(q2² + q3²))
```

#### `vehicle_attitude_setpoint`

Desired attitude from the position or attitude controller.

| Field          | Type     | Units | Description                              |
|----------------|----------|-------|------------------------------------------|
| `roll_body`    | float    | rad   | Desired roll (some firmware versions)    |
| `pitch_body`   | float    | rad   | Desired pitch                            |
| `yaw_body`     | float    | rad   | Desired yaw                              |
| `q_d[4]`       | float[4] | —     | Desired quaternion (newer firmware)      |
| `thrust_body[3]`| float[3]| N     | Desired thrust vector in body frame      |
| `fw_control_yaw_wheel` | bool | — | Fixed-wing: use wheel for yaw control |

#### `vehicle_angular_velocity`

High-rate angular velocity from gyroscope (after filtering).

| Field     | Type     | Units  | Description                  |
|-----------|----------|--------|------------------------------|
| `xyz[3]`  | float[3] | rad/s  | Roll, pitch, yaw rates       |
| `xyz_derivative[3]` | float[3] | rad/s² | Angular acceleration    |

#### `vehicle_rates_setpoint`

Desired angular rates from the attitude controller.

| Field    | Type  | Units  | Description       |
|----------|-------|--------|-------------------|
| `roll`   | float | rad/s  | Desired roll rate  |
| `pitch`  | float | rad/s  | Desired pitch rate |
| `yaw`    | float | rad/s  | Desired yaw rate   |
| `thrust_body[3]` | float[3] | — | Desired thrust vector |

### 2.5 Vehicle Status and Mode

#### `vehicle_status`

Overall vehicle state machine and arming status.

| Field                   | Type    | Description                                          |
|-------------------------|---------|------------------------------------------------------|
| `nav_state`             | uint8_t | Current navigation state (see nav_state enum)        |
| `main_state`            | uint8_t | Main state (see main_state enum below)               |
| `arming_state`          | uint8_t | 0=Init, 1=Standby, 2=Armed, 3=Armed_Error, 4=Standby_Error, 5=Reboot, 6=In_Air_Restore |
| `hil_state`             | uint8_t | 0=Off, 1=Sensor, 2=Full                              |
| `failsafe`              | bool    | True if in failsafe mode                             |
| `is_vtol`               | bool    | True if vehicle is VTOL                              |
| `is_vtol_tailsitter`    | bool    | True if VTOL is tailsitter configuration             |
| `in_transition_mode`    | bool    | True if VTOL is transitioning                        |
| `rc_signal_lost`        | bool    | True if RC signal is lost                            |
| `data_link_lost`        | bool    | True if data link (telemetry) lost                   |
| `mission_failure`       | bool    | True if mission execution failed                     |
| `geofence_violated`     | bool    | True if geofence was violated                        |

**main_state values:**

| Value | Name          |
|-------|---------------|
| 0     | Manual        |
| 1     | Altitude      |
| 2     | Position      |
| 3     | Mission       |
| 4     | Hold          |
| 5     | Return        |
| 6     | Acro          |
| 7     | Offboard      |
| 8     | Stabilized    |
| 9     | Rattitude     |
| 10    | Takeoff       |
| 11    | Land          |
| 12    | Follow Target |
| 13    | Precision Land|
| 14    | Orbit         |

### 2.6 Motor and Actuator Outputs

#### `actuator_outputs`

Raw PWM/analog output values sent to ESCs or servos.

| Field         | Type        | Units | Description                                    |
|---------------|-------------|-------|------------------------------------------------|
| `noutputs`    | uint32_t    | —     | Number of active outputs                       |
| `output[16]`  | float[16]   | µs    | PWM values (typically 1000–2000 µs for motors) |

**Normalization to 0–1:** `(output[i] - 1000) / 1000`

#### `actuator_motors` (PX4 v1.13+)

Normalized motor commands from the allocation layer.

| Field         | Type      | Units | Description                                      |
|---------------|-----------|-------|--------------------------------------------------|
| `control[12]` | float[12] | —     | Motor commands, range −1.0 to +1.0 (or 0 to 1)  |
| `reversible_flags` | uint16_t | — | Bitmask indicating reversible motors           |

**Normalization to 0–1:** `(control[i] + 1.0) / 2.0`

#### `actuator_controls_0` through `actuator_controls_3`

Mixed control inputs before allocation. Group 0 = multirotor/fixed-wing primary.

| Field        | Type     | Units | Description                                         |
|--------------|----------|-------|-----------------------------------------------------|
| `control[8]` | float[8] | —     | [roll, pitch, yaw, thrust, flaps, spoilers, airbrakes, landing_gear] |

### 2.7 Battery

#### `battery_status`

| Field                    | Type    | Units | Description                                   |
|--------------------------|---------|-------|-----------------------------------------------|
| `voltage_v`              | float   | V     | Measured pack voltage (unfiltered)            |
| `voltage_filtered_v`     | float   | V     | Filtered pack voltage                         |
| `current_a`              | float   | A     | Measured current (unfiltered)                 |
| `current_filtered_a`     | float   | A     | Filtered current                              |
| `current_average_a`      | float   | A     | Average current since arming                  |
| `discharged_mah`         | float   | mAh   | Charge discharged since arming                |
| `remaining`              | float   | —     | Remaining capacity fraction (0.0–1.0)         |
| `scale`                  | float   | —     | Power scaling factor                          |
| `time_remaining_s`       | float   | s     | Estimated time remaining                      |
| `average_time_to_empty`  | float   | s     | Rolling average time to empty                 |
| `temperature`            | float   | °C    | Battery temperature                           |
| `cell_count`             | uint8_t | —     | Number of cells (0 = unknown)                 |
| `connected`              | bool    | —     | True if battery is connected                  |
| `system_source`          | bool    | —     | True if this is the main system power source  |
| `warning`                | uint8_t | —     | 0=None, 1=Low, 2=Critical, 3=Emergency, 4=Failed |
| `faults`                 | uint32_t| —     | Fault bitmask (BMS data)                      |

**Per-cell voltage thresholds (LiPo):**

| Level     | Per-cell voltage | 4S pack voltage |
|-----------|-----------------|-----------------|
| Full      | 4.20 V          | 16.8 V          |
| Nominal   | 3.80 V          | 15.2 V          |
| Warning   | 3.50 V          | 14.0 V          |
| Critical  | 3.30 V          | 13.2 V          |
| Emergency | 3.00 V          | 12.0 V          |
| Damage    | < 3.00 V        | < 12.0 V        |

### 2.8 RC Input

#### `input_rc`

| Field              | Type         | Units | Description                               |
|--------------------|--------------|-------|-------------------------------------------|
| `timestamp_last_signal` | uint64_t | µs  | Timestamp of last valid signal            |
| `channel_count`    | uint8_t      | —     | Number of RC channels                     |
| `rssi`             | uint8_t      | %     | Signal strength (0–100), 0 = no signal    |
| `rc_lost`          | bool         | —     | True if RC signal is currently lost       |
| `rc_lost_frame_count` | uint16_t  | —     | Count of lost frames                      |
| `rc_total_frame_count` | uint16_t | —     | Total frames received                     |
| `rc_ppm_frame_length` | uint16_t  | µs    | PPM frame length                          |
| `values[18]`       | uint16_t[18] | µs    | Channel values (typically 1000–2000 µs)   |
| `failsafe`         | bool         | —     | True if RC is in failsafe state           |
| `input_source`     | uint8_t      | —     | 0=Unknown, 1=PPM, 2=SBUS, 3=SPEKTRUM, 4=SUMD, 5=ST24, 6=RCANDUSB, 7=GHST, 8=MAVLINK |

### 2.9 EKF / Estimator State

#### `estimator_status` (legacy, used through ~PX4 v1.12)

| Field                         | Type       | Units | Description                                        |
|-------------------------------|------------|-------|----------------------------------------------------|
| `pos_horiz_accuracy`          | float      | m     | Horizontal position accuracy                       |
| `pos_vert_accuracy`           | float      | m     | Vertical position accuracy                         |
| `mag_test_ratio`              | float      | —     | Magnetometer innovation consistency test ratio      |
| `vel_test_ratio`              | float      | —     | Velocity innovation consistency test ratio          |
| `pos_test_ratio`              | float      | —     | Position innovation consistency test ratio          |
| `hgt_test_ratio`              | float      | —     | Height innovation consistency test ratio            |
| `tas_test_ratio`              | float      | —     | True airspeed innovation consistency test ratio     |
| `hagl_test_ratio`             | float      | —     | Height above ground innovation test ratio           |
| `flow_test_ratio`             | float      | —     | Optical flow innovation test ratio                  |
| `filter_fault_flags`          | uint32_t   | —     | Bitmask of EKF internal fault conditions            |
| `solution_status_flags`       | uint32_t   | —     | EKF solution quality flags                          |
| `control_mode_flags`          | uint32_t   | —     | EKF active sensor fusion modes                      |
| `innovation_check_flags`      | uint32_t   | —     | Innovation consistency check failures (bitmask)     |
| `pos_horiz_drift_m`           | float      | m     | Horizontal position drift in GPS-denied flight      |
| `pos_vert_drift_m`            | float      | m     | Vertical position drift                             |
| `vibe[3]`                     | float[3]   | m/s²  | Vibration metric per axis (coning, swirl, squish)   |
| `time_slip`                   | float      | s     | Estimator time slip                                 |

#### `estimator_innovations` (PX4 v1.13+)

Separate topic replacing the innovation fields in `estimator_status`.

| Field                  | Type     | Units | Description                                  |
|------------------------|----------|-------|----------------------------------------------|
| `gps_hvel[2]`          | float[2] | m/s   | GPS horizontal velocity innovation (NE)      |
| `gps_vvel`             | float    | m/s   | GPS vertical velocity innovation             |
| `gps_hpos[2]`          | float[2] | m     | GPS horizontal position innovation (NE)      |
| `gps_vpos`             | float    | m     | GPS vertical position innovation             |
| `baro_vpos`            | float    | m     | Barometer vertical position innovation       |
| `mag_field[3]`         | float[3] | Gauss | Magnetometer field innovation (XYZ)          |
| `heading`              | float    | rad   | Heading innovation                           |
| `airspeed`             | float    | m/s   | Airspeed innovation                          |
| `flow[2]`              | float[2] | rad/s | Optical flow innovation                      |
| `hagl`                 | float    | m     | Height above ground innovation               |

#### `estimator_status_flags` (PX4 v1.13+)

Replaces bitfield flags from `estimator_status`.

| Field                        | Type     | Description                                          |
|------------------------------|----------|------------------------------------------------------|
| `cs_gps`                     | bool     | GPS being used in fusion                             |
| `cs_opt_flow`                | bool     | Optical flow being used                              |
| `cs_mag_hdg`                 | bool     | Magnetometer heading being used                      |
| `cs_mag_3D`                  | bool     | 3D magnetometer fusion active                        |
| `cs_rng_hgt`                 | bool     | Range finder altitude fusion active                  |
| `cs_baro_hgt`                | bool     | Barometer altitude fusion active                     |
| `cs_gps_hgt`                 | bool     | GPS altitude fusion active                           |
| `cs_ev_pos`                  | bool     | External vision position fusion active               |
| `fs_bad_mag_yaw`             | bool     | Bad magnetometer yaw fault                           |
| `fs_bad_airspeed`            | bool     | Bad airspeed fault                                   |

**Innovation test ratio thresholds (from PX4 EKF2):**

| Ratio     | Interpretation                                              |
|-----------|-------------------------------------------------------------|
| < 0.5     | Healthy — sensor agrees well with EKF prediction            |
| 0.5–0.8   | Elevated — minor sensor/model disagreement                  |
| 0.8–1.0   | Warning — approaching rejection threshold                   |
| > 1.0     | Critical — sensor data being rejected by EKF                |

The EKF rejects measurements when the test ratio exceeds a configurable threshold (default 1.0).
Rejection is logged as fault flags and may cause the EKF to fall back to other sensors.

### 2.10 CPU Load

#### `cpuload`

| Field        | Type  | Units | Description                                    |
|--------------|-------|-------|------------------------------------------------|
| `load`       | float | 0–1   | CPU load fraction (multiply by 100 for %)      |
| `ram_usage`  | float | 0–1   | RAM usage fraction                             |

**CPU load thresholds:**
- < 0.7 (70%): Normal
- 0.7–0.85 (70–85%): Elevated; may cause scheduling jitter
- > 0.85 (85%): Dangerous; likely causing control loop delays and log dropouts

### 2.11 Position Setpoints

#### `vehicle_local_position_setpoint`

| Field      | Type  | Units | Description                                  |
|------------|-------|-------|----------------------------------------------|
| `x`        | float | m     | Desired North position                       |
| `y`        | float | m     | Desired East position                        |
| `z`        | float | m     | Desired Down position (negative = above ref) |
| `vx`       | float | m/s   | Desired North velocity                       |
| `vy`       | float | m/s   | Desired East velocity                        |
| `vz`       | float | m/s   | Desired Down velocity                        |
| `yaw`      | float | rad   | Desired heading                              |
| `yawspeed` | float | rad/s | Desired yaw rate                             |
| `acceleration[3]` | float[3] | m/s² | Desired acceleration (feedforward)  |

---

## 3. Flight Log Analysis Methodology

### 3.1 General Approach

PX4's recommended analysis workflow (as used by Flight Review):

1. **Check for log validity** — verify timestamps are monotonic, no excessive dropouts
2. **Review logged messages** — search for ERROR/WARNING level log entries
3. **Check EKF health first** — if EKF is poor, all other analysis is suspect
4. **Vibration analysis** — precondition for reliable EKF and attitude control
5. **GPS health** — satellite count, HDOP, fix type
6. **Attitude tracking** — actual vs setpoint error and oscillation
7. **Motor outputs** — saturation, imbalance, failure signatures
8. **Battery health** — voltage curve, sag, remaining capacity
9. **Crash analysis** — correlate multiple signals for classification

### 3.2 Log Quality Checks

**Dropout analysis:** Count `O` (Dropout) messages. Each contains a duration in milliseconds.
- Isolated brief dropouts (< 50 ms): normal, caused by logging system
- Frequent or long dropouts: indicate CPU overload, SD card issues, or EMI

**Parameter consistency:** Compare parameters at the beginning of the log with any mid-flight
`P` messages — unexpected mid-flight parameter changes indicate a problem.

**Timestamp continuity:** Check that `timestamp` values in sensor topics are monotonically
increasing and spaced consistently. Gaps or reversals indicate hardware issues.

### 3.3 PID Tuning Quality Assessment

A well-tuned multirotor shows:
- Roll/pitch tracking error RMS < 2–3 degrees in normal flight
- No visible high-frequency oscillation in angular rates
- Motor outputs roughly balanced (within 15% of each other in hover)
- Angular rate setpoint closely tracks actual rates

Signs of poor PID tuning:
- High-frequency oscillation in `vehicle_angular_velocity` or `vehicle_rates_setpoint`
- Large, persistent attitude tracking errors
- Motor outputs clustered at the saturation boundary
- Excessive vibration that may be control-induced

---

## 4. Failure Mode Signatures

### 4.1 Motor Failure

**Diagnostic topics:**
- `actuator_outputs` / `actuator_motors`: one motor drops to minimum while others increase
- `vehicle_attitude`: roll/pitch diverges from setpoint
- `vehicle_rates_setpoint`: controller demands extreme rates on affected axes

**Signature pattern:**
1. One motor output drops to near-zero or saturates at maximum
2. Other motors increase output to compensate (visible as imbalance spike)
3. Yaw disturbance (if motor failure changes moment arm)
4. Attitude divergence follows within 0.5–2.0 seconds
5. Rapid altitude loss

**PX4 motor failure detection parameters:**
- `COM_MOT_DEADZONE`: PWM deadzone — outputs below this are considered "off"
- Motor failure is detected when the power loss estimate exceeds `FW_MOTOR_FAIL_THR`

**Distinguishing single motor from ESC/power rail failure:**
- Single motor failure: only one output drops, others compensate (imbalance)
- ESC failure: motor ramps to maximum, then cuts — often shows brief spike before dropout
- Power rail: all motors on a BEC circuit drop simultaneously

### 4.2 Power Loss / Battery Failure

**Signature pattern:**
1. `battery_status.voltage_v` drops sharply (> 1.5 V in < 2 s)
2. All motor outputs simultaneously drop to zero or minimum
3. `actuator_outputs` shows no further updates
4. Log typically ends abruptly (no graceful disarm sequence)

**Brownout pattern (voltage collapses under load):**
1. High current demand (maneuver or heavy hover)
2. Voltage sag exceeds 2+ V
3. Flight controller reboots mid-flight (log ends, may restart with new log)
4. No controlled disarm event

### 4.3 GPS Loss / Position Estimation Failure

**Diagnostic topics:**
- `vehicle_gps_position` or `sensor_gps`: `fix_type` drops below 3, `satellites_used` drops
- `estimator_status`: `pos_test_ratio` or `vel_test_ratio` spikes above 1.0
- `vehicle_local_position`: `xy_valid` or `xy_global` flags go false
- `vehicle_status`: mode changes to Return or Land (failsafe triggered)

**Signature pattern:**
1. `satellites_used` drops below threshold
2. `eph` increases (position accuracy degrades)
3. EKF innovation ratios for GPS position/velocity spike
4. `cs_gps` fusion flag clears
5. Autopilot may switch to altitude hold or trigger failsafe
6. If in mission: mission abort or RTL

**GPS multipath / jamming:**
- `jamming_indicator` > 0
- Position jumps (non-physical movement between consecutive samples)
- `eph` oscillates rapidly without consistent trend

### 4.4 Vibration-Induced Failures

**High vibration can cause:**
- IMU data corruption (aliasing from under-sampled high-frequency content)
- EKF divergence (noisy accelerometer → poor altitude/position estimation)
- Harmonic resonance with PID loop → oscillation
- Sensor clipping (`accelerometer_clipping` flag set)

**Vibration failure signatures:**
1. `sensor_combined.accelerometer_m_s2` shows broadband noise > 15 m/s²
2. `estimator_status.vibe[0-2]` metrics elevated (> 15 m/s² warning, > 30 m/s² bad)
3. Altitude hold becomes unstable (oscillating `vehicle_local_position.z`)
4. `accelerometer_clipping` bits set during flight

### 4.5 Control Loop Oscillation

**Identifying oscillations:**
- Compare `vehicle_angular_velocity.xyz` with `vehicle_rates_setpoint`
- High-frequency sign changes in the error signal indicate oscillation
- Frequency analysis (FFT) of gyro data reveals dominant oscillation frequencies

**PX4 oscillation frequency ranges:**
- < 5 Hz: probably slow attitude oscillation (P gain too high in attitude loop)
- 5–30 Hz: angular rate oscillation (rate P/D gains too high)
- > 30 Hz: structural / propeller resonance (mechanical issue or insufficient filtering)
- 100–400 Hz: motor/ESC resonance band (addressed by notch filters)

### 4.6 Compass / Magnetometer Failure

**Diagnostic topics:**
- `estimator_status.mag_test_ratio`: > 1.0 indicates rejection
- `estimator_status_flags.fs_bad_mag_yaw`: explicit fault flag
- `vehicle_attitude`: yaw jumps or oscillates

**Signature pattern:**
1. `mag_test_ratio` spikes during motor spin-up (motor EMI interference)
2. Yaw heading shows sudden jumps
3. EKF may switch to GNSS heading if available
4. In-flight compass interference causes gradual yaw drift

### 4.7 RC Failsafe

**Triggered when:**
- `input_rc.rc_lost` = true for more than `COM_RC_LOSS_T` seconds (default 0.5 s)
- `input_rc.failsafe` = true (receiver-level failsafe)

**Response depends on `NAV_RCL_ACT` parameter:**
- 0: Disabled (dangerous — no action)
- 1: Loiter
- 2: Return to Launch
- 3: Land
- 4: Terminate
- 5: Lockdown

**Log signature:** `vehicle_status.rc_signal_lost` = true, followed by mode change
to return/land/loiter depending on configuration.

---

## 5. Filter Tuning and Vibration Analysis

### 5.1 IMU Filter Architecture

PX4 applies a cascade of filters to gyroscope data before it reaches the PID controller:

```
Raw Gyro → Low-pass Filter (LPF) → Notch Filter(s) → PID Controller
```

For accelerometers (used by EKF):
```
Raw Accel → Low-pass Filter → EKF
```

### 5.2 Key Filter Parameters

#### Gyroscope Low-Pass Filter

| Parameter           | Default | Range    | Description                                      |
|---------------------|---------|----------|--------------------------------------------------|
| `IMU_GYRO_CUTOFF`   | 40 Hz   | 5–400 Hz | Gyro low-pass filter cutoff frequency            |
| `IMU_GYRO_NF0_FRQ`  | 0 Hz    | 0–1000 Hz| Notch filter 0 center frequency (0 = disabled)  |
| `IMU_GYRO_NF0_BW`   | 20 Hz   | 1–100 Hz | Notch filter 0 bandwidth                         |
| `IMU_GYRO_NF1_FRQ`  | 0 Hz    | 0–1000 Hz| Notch filter 1 center frequency                  |
| `IMU_GYRO_NF1_BW`   | 20 Hz   | 1–100 Hz | Notch filter 1 bandwidth                         |

#### Accelerometer Low-Pass Filter

| Parameter           | Default  | Range     | Description                               |
|---------------------|----------|-----------|-------------------------------------------|
| `IMU_ACCEL_CUTOFF`  | 30 Hz    | 5–200 Hz  | Accel low-pass filter cutoff frequency    |

#### Dynamic Notch Filter (RPM-based)

PX4 supports dynamic notch filters that track motor RPM via ESC telemetry:

| Parameter                 | Default | Description                                     |
|---------------------------|---------|-------------------------------------------------|
| `IMU_GYRO_DNF_EN`         | 0       | Enable dynamic notch (bitmask: 1=IMU, 2=throttle) |
| `IMU_GYRO_DNF_MIN`        | 80 Hz   | Minimum frequency for dynamic notch              |
| `IMU_GYRO_DNF_BW`         | 15 Hz   | Bandwidth of each dynamic notch                  |
| `IMU_GYRO_DNF_HLTC`       | 2.5     | Harmonics to filter (default 2.5 = 1st and 2nd) |

### 5.3 PID Rate Controller Filter Parameters

| Parameter              | Default  | Description                                        |
|------------------------|----------|----------------------------------------------------|
| `MC_ROLLRATE_D_TF`     | 0.0 s    | Roll rate D-term setpoint weight                   |
| `MC_PITCHRATE_D_TF`    | 0.0 s    | Pitch rate D-term setpoint weight                  |
| `MC_YAWRATE_D_TF`      | 0.0 s    | Yaw rate D-term time constant                      |

### 5.4 Vibration Thresholds from PX4

PX4 Flight Review uses the `vibe` metric from `estimator_status` to classify vibration.
These are computed from the EKF accel delta-velocity measurements:

| Level    | vibe[0] (coning) | vibe[1] (swirl)  | vibe[2] (squish) |
|----------|-----------------|-----------------|-----------------|
| Good     | < 15 m/s²       | < 15 m/s²       | < 15 m/s²       |
| Warning  | 15–30 m/s²      | 15–30 m/s²      | 15–30 m/s²      |
| Bad      | > 30 m/s²       | > 30 m/s²       | > 30 m/s²       |

**Raw accelerometer RMS thresholds (from `sensor_combined`):**

| Level    | Horizontal axes (X, Y) | Vertical axis (Z, gravity-removed) |
|----------|----------------------|-------------------------------------|
| Good     | < 15 m/s²            | < 15 m/s²                           |
| Warning  | 15–30 m/s²           | 15–30 m/s²                          |
| Bad      | > 30 m/s²            | > 30 m/s²                           |

**Typical IMU sensor saturation level:** ±16 g (≈ ±156.9 m/s²). Samples near this value
indicate sensor clipping and unreliable data.

### 5.5 Frequency Analysis for Vibration

The recommended approach for vibration diagnosis is FFT analysis of the raw gyro signal:

1. Extract `sensor_combined.gyro_rad[0]` (roll axis, highest sensitivity to props)
2. Apply FFT with windowing (Hann window recommended)
3. Look for peaks in the spectrum:
   - Motor frequency = RPM/60 Hz (typ. 50–200 Hz for multirotors)
   - 2× motor frequency (first harmonic — blade pass)
   - Frame resonance (low-frequency peak, 20–80 Hz, vehicle-dependent)

**Motor frequency estimation:** For a 4-pole motor at 12,000 RPM → 200 Hz fundamental,
400 Hz first harmonic. For a typical 6-inch prop quad at half throttle → ~80–120 Hz.

**Action based on spectral peaks:**
- Narrow peak at motor frequency: prop imbalance → balance props
- Broad peak 20–60 Hz: frame resonance → add vibration damping
- Peak tracks throttle: motor/prop imbalance → check motor mounting, bearing wear
- Multiple harmonics visible: severe resonance or loose component

### 5.6 Filter Tuning Decision Logic

```
IF peak_frequency is known and above 80 Hz:
    Add static notch filter at that frequency (IMU_GYRO_NF0_FRQ = peak_freq)
    Set bandwidth = peak_freq × 0.2 (typ. 15–20 Hz for narrow peaks)

IF spectrum is broadband and noisy:
    Lower IMU_GYRO_CUTOFF (from 40 Hz toward 20–30 Hz)
    NOTE: lower cutoff adds phase delay → may require lower P/D gains

IF using ESC telemetry (DSHOT with bidirectional ESC):
    Enable IMU_GYRO_DNF_EN = 1 for automatic RPM tracking
    This eliminates need for static notch filters
```

---

## 6. EKF Health and Innovation Monitoring

### 6.1 EKF2 Architecture

PX4 uses the `EKF2` estimator, a 24-state Extended Kalman Filter fusing:
- IMU (gyroscope + accelerometer) — always active
- GPS position and velocity
- Barometer altitude
- Magnetometer heading
- Airspeed (fixed-wing)
- Optical flow
- External vision (VICON/mocap)
- Range finder altitude

### 6.2 Innovation Consistency Tests

The EKF runs consistency tests on each measurement before fusing it. The test ratio is:

```
test_ratio = innovation² / (innovation_variance + measurement_noise²)
```

Ratios > 1.0 cause the measurement to be **rejected**. Innovation ratios are found in:
- `estimator_status.vel_test_ratio` — GPS velocity
- `estimator_status.pos_test_ratio` — GPS position
- `estimator_status.hgt_test_ratio` — Height (baro or GPS)
- `estimator_status.mag_test_ratio` — Magnetometer
- `estimator_status.tas_test_ratio` — True airspeed
- `estimator_status.hagl_test_ratio` — Height above ground (rangefinder)
- `estimator_innovations.*` — per-measurement innovations (v1.13+)

**Diagnosis when ratios are elevated:**
- Persistent `vel_test_ratio` > 0.8: GPS velocity noise, poor satellite geometry, interference
- Persistent `pos_test_ratio` > 0.8: GPS multipath, poor environment (urban canyon)
- Persistent `hgt_test_ratio` > 0.8: barometer drift, pressure shock from payload
- Persistent `mag_test_ratio` > 0.8: motor EMI, ferrous metal nearby, miscalibration

### 6.3 EKF Fault Flags

`estimator_status.filter_fault_flags` is a bitmask. Key bits (hex):

| Bit | Mask   | Meaning                                                    |
|-----|--------|------------------------------------------------------------|
| 0   | 0x0001 | IMU delta velocity data was bad                            |
| 1   | 0x0002 | IMU delta angle data was bad                               |
| 2   | 0x0004 | Height data above maximum rate                             |
| 3   | 0x0008 | Magnetometer data above maximum rate                       |
| 4   | 0x0010 | GPS data above maximum rate                                |
| 5   | 0x0020 | Airspeed data above maximum rate                           |
| 6   | 0x0040 | Synthetic sideslip data above maximum rate                 |
| 7   | 0x0080 | Height source selector changed mid-flight                  |
| 8   | 0x0100 | Delta velocity data is bad                                 |
| 9   | 0x0200 | Bad imu bias (IMU inconsistency)                           |
| 10  | 0x0400 | Wind velocity estimate is bad                              |
| 11  | 0x0800 | Magnetometer bias is bad                                   |

`estimator_status.solution_status_flags` — solution quality bitmask:

| Bit | Mask   | Meaning (bit SET = problem)                                |
|-----|--------|------------------------------------------------------------|
| 0   | 0x0001 | Attitude estimate is good                                  |
| 1   | 0x0002 | Horizontal velocity estimate is good                       |
| 2   | 0x0004 | Vertical velocity estimate is good                         |
| 3   | 0x0008 | Horizontal position relative estimate is good              |
| 4   | 0x0010 | Horizontal position absolute (GPS) estimate is good        |
| 5   | 0x0020 | Vertical position absolute estimate is good                |
| 6   | 0x0040 | Vertical position above ground estimate is good            |
| 7   | 0x0080 | Constant position mode (no motion estimate)                |
| 8   | 0x0100 | Predicted horizontal position (after GPS loss) is good     |
| 9   | 0x0200 | EKF is using GPS                                           |
| 10  | 0x0400 | EKF is using optical flow                                  |
| 11  | 0x0800 | EKF is using vision position                               |
| 12  | 0x1000 | EKF is using vision yaw                                    |
| 13  | 0x2000 | EKF is using external vision velocity                      |
| 14  | 0x4000 | EKF is using barometric height                             |
| 15  | 0x8000 | EKF is using range finder height                           |

### 6.4 `estimator_status.vibe` Metrics

Three vibration-related metrics in `estimator_status`:

| Index | Name    | Meaning                                                           |
|-------|---------|-------------------------------------------------------------------|
| 0     | Coning  | Vibration producing coning motion (X²+Y² integral of delta-vel)  |
| 1     | Swirl   | Vibration producing swirl (XY integral of delta-vel)             |
| 2     | Squish  | Vibration producing squish (Z integral of delta-vel)             |

These are computed from the delta-velocity measurements in the EKF predict step. They reflect
how much vibration energy is aliasing into the EKF state estimates.

---

## 7. GPS and Position Estimation

### 7.1 GPS Quality Criteria

PX4 uses these criteria to decide whether to allow GPS-based navigation:

| Parameter              | Default | Description                                          |
|------------------------|---------|------------------------------------------------------|
| `EKF2_GPS_CHECK`       | 245     | Bitmask of GPS quality checks to perform             |
| `EKF2_REQ_EPH`         | 3.0 m   | Maximum acceptable horizontal accuracy               |
| `EKF2_REQ_EPV`         | 5.0 m   | Maximum acceptable vertical accuracy                 |
| `EKF2_REQ_SACC`        | 1.0 m/s | Maximum acceptable speed accuracy                    |
| `EKF2_REQ_HACC`        | 0.5 m   | Maximum horizontal drift before declaring poor       |
| `EKF2_REQ_VACC`        | 0.8 m   | Maximum vertical drift                               |
| `EKF2_REQ_HDRIFT`      | 0.1 m/s | Horizontal drift limit (static GPS test)             |
| `EKF2_REQ_VDRIFT`      | 0.2 m/s | Vertical drift limit                                 |
| `EKF2_REQ_NSATS`       | 6       | Minimum number of satellites                         |
| `EKF2_REQ_GDOP`        | 2.5     | Maximum GDOP acceptable                              |

### 7.2 GPS Check Bitmask (`EKF2_GPS_CHECK`)

| Bit | Meaning                                        |
|-----|------------------------------------------------|
| 0   | Minimum satellite count                        |
| 1   | HDOP                                           |
| 2   | VDOP                                           |
| 3   | Horizontal speed accuracy (SACC)               |
| 4   | Vertical accuracy (EPV)                        |
| 5   | Horizontal accuracy (EPH)                      |
| 6   | Horizontal drift (test at GPS fix)             |
| 7   | Vertical drift                                 |

### 7.3 HDOP Interpretation

| HDOP     | Rating    | Notes                                              |
|----------|-----------|----------------------------------------------------|
| 1.0      | Ideal     | Best possible geometry                             |
| 1–2      | Excellent | Highly accurate horizontal position                |
| 2–5      | Good      | Adequate for most applications                     |
| 5–10     | Moderate  | Use with caution for critical navigation           |
| 10–20    | Fair      | Low confidence, large error possible               |
| > 20     | Poor      | Inaccurate, not recommended for autonomous flight  |

---

## 8. Battery and Power Analysis

### 8.1 LiPo Battery Chemistry

LiPo cell discharge characteristics:

| State of Charge | Cell Voltage | Notes                                      |
|-----------------|-------------|--------------------------------------------|
| 100%            | 4.20 V      | Full charge                                |
| 80%             | 3.95 V      | Typical "storage charge"                   |
| 50%             | 3.75 V      | Mid-discharge                              |
| 20%             | 3.55 V      | Approaching warning level                  |
| 10%             | 3.45 V      | Warning level (land soon)                  |
| 5%              | 3.30 V      | Critical level (land immediately)          |
| Empty           | 3.00 V      | Hard cutoff — cell damage risk             |

### 8.2 Internal Resistance and Voltage Sag

Voltage sag under load = `I × R_internal` where R_internal increases with:
- Cell age (cycle count)
- Low state of charge
- Low temperature
- High C-rate demand

**Sag thresholds:**
- < 0.3 V sag at 10–15A: fresh, healthy pack
- 0.3–0.8 V sag: mild aging, still serviceable
- 0.8–1.5 V sag: significant aging, reduced capacity and performance
- > 1.5 V sag: pack should be retired (brownout risk)

### 8.3 PX4 Battery Failsafe Parameters

| Parameter              | Default | Description                                               |
|------------------------|---------|-----------------------------------------------------------|
| `BAT_LOW_THR`          | 0.15    | Remaining fraction triggering low battery warning         |
| `BAT_CRIT_THR`         | 0.07    | Remaining fraction triggering critical battery failsafe   |
| `BAT_EMERGEN_THR`      | 0.05    | Remaining fraction triggering emergency landing           |
| `COM_LOW_BAT_ACT`      | 0       | Action on low battery: 0=Warn, 1=Warn+RTL, 2=RTL, 3=Land |
| `BAT_V_CHARGED`        | 4.05 V  | Voltage considered fully charged (per cell)               |
| `BAT_V_EMPTY`          | 3.50 V  | Voltage considered empty (per cell)                       |
| `BAT_CAPACITY`         | -1      | Battery capacity in mAh (-1 = auto)                       |
| `BAT_N_CELLS`          | 0       | Number of cells (0 = auto-detect)                         |
| `BAT_R_INTERNAL`       | -1      | Internal resistance for compensation (-1 = auto)          |

---

## 9. Motor and Actuator Analysis

### 9.1 Motor Output Interpretation

For a quadrotor in hover, ideal motor outputs are:

- **All equal** at approximately 50% throttle (0.5 normalized)
- **Hover throttle** typically 40–60% of max; characterised by `MPC_THR_HOVER` parameter
- **Maximum sustained output** for safety margin: < 80% in hover

**Saturation analysis rules:**
- Any motor > 95% normalized output = saturated (flight controller loses authority on that motor)
- Saturation during aggressive maneuvers: acceptable briefly
- Saturation in hover: indicates underpowered craft, improper CG, or mechanical problem
- Sustained saturation (> 3 s): critical — loss of control margin

### 9.2 Motor Imbalance Indicators

For a X-frame quadrotor, the PX4 mixer assigns:
- Motor 0 (front-right): CW
- Motor 1 (back-left): CW
- Motor 2 (front-left): CCW
- Motor 3 (back-right): CCW

**Acceptable imbalance patterns:**
- Slight imbalance due to CG offset: diagonal pair (0+1) vs (2+3) runs higher
- Yaw bias: one rotation direction runs higher than the other rotation direction
- More than 15% persistent spread: investigate CG, motor mount level, frame twist

### 9.3 ESC Telemetry (via `esc_status`)

When using DSHOT with bidirectional ESC telemetry, `esc_status` provides per-motor data:

| Field            | Type          | Units | Description                            |
|------------------|---------------|-------|----------------------------------------|
| `esc_rpm[8]`     | int32_t[8]    | RPM   | Motor RPM per ESC                      |
| `esc_voltage[8]` | float[8]      | V     | BEC/ESC input voltage per ESC          |
| `esc_current[8]` | float[8]      | A     | Current draw per ESC                   |
| `esc_temperature[8]` | float[8] | °C    | ESC temperature per ESC                |
| `esc_errorcount[8]`  | uint32_t[8]| — | Error count per ESC                    |
| `counter`        | uint8_t       | —     | Update counter                         |

**ESC RPM analysis:**
- Plot RPM vs throttle command: should be linear
- RPM deviation between motors: > 5% at same command = motor/prop mismatch
- RPM oscillation at constant throttle: prop imbalance or bearing wear
- ESC error count increasing: connection issue, damaged ESC

---

## 10. RC and Failsafe Analysis

### 10.1 RC Signal Quality

PX4 receives RC via UART/PPM/SBUS. `input_rc.rssi` is 0–100 where:
- 100 = maximum signal strength
- 0 = no signal (failsafe condition)

Note: RSSI is receiver-provided and protocols differ. Some receivers always report 100 until
total loss. RSSI from FrSky/ELRS/Crossfire is more meaningful than PPM/SBUS RSSI.

### 10.2 Failsafe Configuration Parameters

| Parameter          | Default | Description                                                |
|--------------------|---------|-------------------------------------------------------------|
| `COM_RC_LOSS_T`    | 0.5 s   | Time before triggering RC loss failsafe                    |
| `NAV_RCL_ACT`      | 2       | RC loss failsafe action (see below)                        |
| `COM_DL_LOSS_T`    | 10 s    | Data link loss timeout before failsafe                     |
| `NAV_DLL_ACT`      | 0       | Data link loss failsafe action                             |
| `GF_ACTION`        | 1       | Geofence breach action                                     |

**`NAV_RCL_ACT` values:**
- 0: Disabled
- 1: Loiter
- 2: Return (default)
- 3: Land
- 4: Terminate
- 5: Lockdown

### 10.3 RC Channel Ranges

Standard RC channel mapping for PX4:

| Channel | Function (default) | Failsafe value |
|---------|-------------------|----------------|
| 1       | Roll              | Centre (1500 µs) |
| 2       | Pitch             | Centre (1500 µs) |
| 3       | Throttle          | Minimum (1000 µs) |
| 4       | Yaw               | Centre (1500 µs) |
| 5       | Mode switch       | Position or as configured |
| 6–18    | Aux/switches      | Hold last or as configured |

---

## 11. Analysis Tools

### 11.1 Flight Review (PX4 Official Web Tool)

URL: `https://review.px4.io`

Flight Review is PX4's primary web-based log analysis tool. It:

- Accepts `.ulg` uploads directly
- Renders interactive time-series plots of all topics
- Performs automated checks with pass/warn/fail indicators
- Specifically checks: vibration levels, EKF consistency, tracking error, GPS quality,
  battery, motor balance, CPU load, log completeness

**Flight Review automated checks (basis for Goose thresholds):**
- Vibration: `estimator_status.vibe` > 15 m/s² = warn, > 30 m/s² = bad
- EKF innovation ratios: > 0.5 = warn, > 1.0 = reject/bad
- Attitude tracking error: > 8° RMS = warn
- CPU load: > 80% = warn
- Dropout percentage: > 5% = warn

**Flight Review source code:** `https://github.com/PX4/flight_review`
The check logic is in `plot_app/helper_functions.py` and is the most authoritative
reference for PX4-recommended thresholds.

### 11.2 PlotJuggler

A desktop time-series visualization tool popular in the PX4 community.

- Install: `sudo snap install plotjuggler` or via ROS
- Has a ULog plugin: import `.ulg` files directly
- Supports drag-and-drop multi-plot layouts
- Useful for custom overlaying: e.g. actual vs setpoint, multiple IMUs

**PlotJuggler advantages over Flight Review:**
- Fully local/offline
- Can overlay arbitrary topic combinations
- Supports Lua scripting for derived metrics
- Better for real-time analysis during development

### 11.3 pyulog / pyFlightAnalysis

**pyulog** (`pip install pyulog`) — the official Python ULog reader. Provides:
- `ulog2csv`: export all topics to CSV
- `ulog_info`: print log metadata and topic list
- `ULog` Python class for programmatic access

**pyFlightAnalysis** — Python library with higher-level analysis functions.
Used by the Goose project indirectly (our ULog parser uses `pyulog`).

### 11.4 px4tools (deprecated)

An older Python library predating pyulog. Mostly superseded by pyulog + pandas workflows.
Some community scripts still reference it. Not recommended for new development.

### 11.5 QGroundControl (GCS)

- Has built-in log viewer accessible from Analyze menu
- Shows raw telemetry plots
- Less powerful than Flight Review for post-hoc analysis
- Useful for checking MAVLink parameter values

### 11.6 Matlab/Simulink

PX4 provides ULog → Matlab import scripts. Used for advanced control design analysis.
Not relevant for Goose (Python ecosystem).

### 11.7 How Flight Review Scores Flights — Analysis We Should Match or Exceed

Flight Review uses a **traffic light system** (green/yellow/red) for each check:

| Check                    | Green           | Yellow              | Red                 |
|--------------------------|-----------------|---------------------|---------------------|
| Vibration (vibe[0])      | < 15 m/s²       | 15–30 m/s²          | > 30 m/s²           |
| EKF vel innovation ratio | < 0.5           | 0.5–1.0             | > 1.0               |
| EKF pos innovation ratio | < 0.5           | 0.5–1.0             | > 1.0               |
| Attitude tracking error  | < 4°            | 4–8°                | > 8°                |
| CPU load                 | < 70%           | 70–80%              | > 80%               |
| Gyro clipping            | 0               | 1–100               | > 100 clips         |
| GPS satellites           | ≥ 9             | 6–8                 | < 6                 |
| HDOP                     | < 1.4           | 1.4–2.0             | > 2.0               |
| Motor output balance     | < 10%           | 10–25%              | > 25%               |
| Battery warning level    | none triggered  | low triggered       | critical triggered  |

---

## 12. Gaps in Current Goose Plugins

Based on the above reference, the following analysis capabilities are not yet present in
the current Goose plugin suite and would improve analysis accuracy:

### 12.1 `estimator_status.vibe` Metrics

The current vibration plugin uses raw `sensor_combined` accelerometer RMS. Flight Review
additionally uses `estimator_status.vibe[0-2]`, which directly reflects vibration energy
entering the EKF. These should be read alongside raw accelerometer data.

**Improvement:** Read `vibe[0]`, `vibe[1]`, `vibe[2]` from `estimator_status` for a
complementary vibration score that directly reflects EKF impact.

### 12.2 Spectral / FFT Vibration Analysis

The current vibration plugin has no frequency-domain analysis. Identifying the dominant
frequency of vibration is essential for filter tuning recommendations.

**Improvement:** Add FFT of `sensor_combined.gyro_rad` to identify motor/prop resonance
frequencies and recommend specific notch filter settings.

### 12.3 Sensor Clipping Detection via `accelerometer_clipping`

The current clipping detection uses a magnitude threshold (`> 156 m/s²`). The ULog topic
`sensor_combined.accelerometer_clipping` provides an explicit hardware clipping flag
(bitmask, per axis). This is more reliable than the magnitude threshold.

**Improvement:** Check `accelerometer_clipping` field directly instead of/in addition to
magnitude threshold.

### 12.4 EKF Innovation Ratio Parsing

The current EKF plugin reads `vel_innov_x/y/z` and `pos_innov_x/y/z` from the normalized
`estimator_status` extraction in the parser. But the actual PX4 fields are:
- `vel_test_ratio` (scalar, worst-axis)
- `pos_test_ratio` (scalar)
- `hgt_test_ratio` (scalar)
- `mag_test_ratio` (scalar)
- `estimator_innovations.*` fields (per-component, PX4 v1.13+)

The parser currently tries to find `vel_innov_x` etc., which may not exist in all firmware
versions. Expanding to also check `vel_test_ratio` and `pos_test_ratio` would improve
compatibility.

### 12.5 ESC Telemetry Analysis (`esc_status`)

No current plugin analyses per-motor RPM, current, or ESC temperature. This data
(available when using DSHOT bidirectional ESC telemetry) is highly valuable for:
- Detecting motor bearing degradation (RPM deviation at fixed throttle)
- ESC thermal issues (temperature trending)
- Per-motor efficiency analysis

### 12.6 GPS Jamming and Spoofing Detection

The GPS health plugin checks satellite count and HDOP but does not check:
- `jamming_indicator` field (GPS hardware anti-jamming metric)
- `spoofing_state` field (GPS spoofing detection)
- `noise_per_ms` (GPS noise metric)

### 12.7 Magnetometer Health

No current plugin analyses compass/magnetometer health. Relevant checks:
- `estimator_status.mag_test_ratio` > 0.5 warning, > 1.0 critical
- `estimator_status_flags.fs_bad_mag_yaw` explicit fault flag
- Yaw heading consistency with GPS track heading (divergence = compass error)
- Motor interference pattern: mag test ratio correlates with motor output changes

### 12.8 Position Tracking Error

No plugin currently compares `vehicle_local_position` against
`vehicle_local_position_setpoint` for mission position error. This is analogous to the
attitude tracking plugin but for position. Relevant for mission execution quality.

### 12.9 CPU Load Trending

The EKF and log quality plugins could benefit from CPU load analysis. High CPU load
causes scheduling jitter which degrades PID loop timing and causes log dropouts. The
correlation between CPU load spikes and log dropouts is a diagnostic indicator.

### 12.10 Barometer Health

No plugin analyses `sensor_baro`:
- Altitude oscillation that doesn't match GPS altitude = baro interference
- Baro altitude drift = pressure leaks in FC enclosure
- Temperature-correlated drift = thermal sensitivity issue
- Error count increasing = sensor hardware degradation

---

*This document was compiled from PX4 official documentation, ULog file format specification,
Flight Review source code analysis, and community analysis practice. It is intended as a
living reference — update as new PX4 versions introduce new topics or change field names.*

*Last updated: 2026-04-06*
