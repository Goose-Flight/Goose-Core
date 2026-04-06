# Sample Flight Logs

This directory contains sample drone flight log files used for testing and developing the Goose crash analysis engine.

## Directory Structure

```
logs/
  px4/
    good_flights/    # Normal, healthy PX4 ULog (.ulg) files
    crashes/         # PX4 logs containing crashes, failsafes, or anomalies
  ardupilot/
    good_flights/    # Normal ArduPilot DataFlash (.bin) or tlog (.tlog) files
    crashes/         # ArduPilot logs containing crashes or anomalies
```

## PX4 Log Sources

- **PX4 Flight Review**: https://review.px4.io — public log database with searchable flight logs
- **PX4 Flight Review API**: `GET https://review.px4.io/api/logs?search=<query>` returns log metadata; download via `GET https://review.px4.io/api/upload/{id}/log`
- **pyulog test data**: The pyulog library repo includes sample .ulg files for unit testing

## ArduPilot Log Sources

- **ArduPilot forums**: https://discuss.ardupilot.org — community members frequently share .bin/.tlog files when reporting crashes
- **ArduPilot log viewer**: https://plotbeta.ardupilot.org

## File Formats

| Format | Extension | Firmware | Parser |
|--------|-----------|----------|--------|
| ULog   | `.ulg`    | PX4      | `goose.parsers.ulog` |
| DataFlash | `.bin` | ArduPilot | `goose.parsers.dataflash` |
| MAVLink telemetry | `.tlog` | Both | `goose.parsers.tlog` |
| CSV export | `.csv` | Any | `goose.parsers.csv_parser` |

## Usage

```bash
# Analyze a single log
goose analyze logs/px4/crashes/example_crash.ulg

# Batch analyze all PX4 crash logs
goose analyze logs/px4/crashes/

# Run crash detection specifically
goose crash logs/px4/crashes/example_crash.ulg
```
