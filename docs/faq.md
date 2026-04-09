# Frequently Asked Questions

## Installation & Setup

### Q: What are the system requirements?
**A:** Goose requires Python 3.10 or newer. It works on Linux, macOS, Windows, and Raspberry Pi. Run `pip install goose-flight` and then verify with `goose doctor`.

### Q: Does Goose work on Windows?
**A:** Yes! Goose is fully cross-platform. Install it the same way: `pip install goose-flight`. All commands work identically on Windows, macOS, and Linux.

### Q: Can I use Goose without an internet connection?
**A:** Yes, completely! Goose is air-gapped by design — it analyzes logs locally with zero network calls. Perfect for field analysis or sensitive environments.

### Q: How much disk space does Goose need?
**A:** The package is lightweight (~50 MB installed). Log files vary: a typical 10-minute flight log is 1-5 MB depending on sensor sampling rates.

---

## Usage & Analysis

### Q: How long does an analysis take?
**A:** Most analyses complete in 2-10 seconds depending on log file size and your hardware. Larger logs or verbose output may take longer.

### Q: What log formats does Goose support?
**A:** Goose supports **PX4 ULog (.ulg)**, **ArduPilot DataFlash (.bin, .log)**, and **generic CSV (.csv)**. A stub parser exists for MAVLink TLog (.tlog) in Core; the real TLog parser ships in Goose Pro. See [Supported Formats](supported-formats.md) for details.

### Q: Can Goose analyze non-drone flight logs?
**A:** Goose is designed for UAV telemetry logs. PX4 ULog, ArduPilot DataFlash, and CSV are all supported in Core. MAVLink TLog requires Goose Pro.

### Q: What does the "Overall Score" mean?
**A:** It's a weighted average across all plugins (0-100). Higher is better. A score below 50 indicates serious issues; below 70 indicates warnings. See [Crash Analysis Guide](crash-analysis-guide.md) for detailed interpretation.

### Q: Why does Goose say "crash detected" when the flight looks fine?
**A:** Goose analyzes sensor data, not visual footage. It may flag high vibration, power sag, or GPS loss even if the drone didn't crash. Read the "Inspect" checklist — it's preventive maintenance, not just crash diagnosis.

### Q: Can I run Goose on many files at once?
**A:** Use a shell loop or script. Example:
```bash
for file in logs/*.ulg; do goose crash "$file" -o "reports/${file%.ulg}.txt"; done
```
See [Advanced Usage](advanced-usage.md) for batch analysis patterns.

---

## Plugins & Customization

### Q: What plugins are included?
**A:** 17 built-in plugins: crash_detection, vibration, battery_sag, gps_health, motor_saturation, ekf_consistency, rc_signal, attitude_tracking, position_tracking, failsafe_events, log_health, payload_change_detection, mission_phase_anomaly, operator_action_sequence, environment_conditions, damage_impact_classification, and link_telemetry_health. Run `goose plugins list` to see all installed plugins.

### Q: Can I write my own plugin?
**A:** Yes! Goose has a plugin architecture. See [Writing Plugins](writing-plugins.md) for the complete guide, including templates and examples.

### Q: Can I disable certain plugins?
**A:** Use `--plugin` with `goose analyze` to run only specific checks:
```bash
goose analyze flight.ulg --plugin vibration --plugin battery_sag
```

### Q: How do I change sensitivity thresholds?
**A:** Edit the configuration file. See [Configuration](configuration.md) for the full list of tunable parameters per plugin.

---

## Reports & Output

### Q: What formats can I export reports in?
**A:** Text (human-readable) and JSON (machine-readable). Use `-f text` or `-f json`:
```bash
goose crash flight.ulg -f json -o report.json
```

### Q: Can I generate PDF reports?
**A:** Not directly. However, you can convert text reports to PDF using tools like `pandoc` or `wkhtmltopdf`, or process JSON output with custom scripts.

### Q: What's the difference between `goose crash` and `goose analyze`?
**A:** `crash` synthesizes all findings into a root cause diagnosis with confidence scoring. `analyze` runs all plugins and shows raw results without synthesis. Use `crash` for quick answers, `analyze` for detailed inspection.

---

## Web Interface

### Q: Is the web dashboard production-ready?
**A:** The web GUI is the primary product surface as of Sprint 2. It supports case-oriented workflow: case creation, evidence upload, analysis, findings view, audit trail, and parse diagnostics. The API may still evolve as new sprints are completed.

### Q: Can I embed Goose analysis in my own application?
**A:** Yes! Use `goose serve` to start the REST API server, or import Goose as a Python library and call the analysis functions directly. See [API Documentation](api-reference.md).

---

## Data & Privacy

### Q: Does Goose upload my log files anywhere?
**A:** No. Goose is 100% local. Your log files never leave your computer.

### Q: Can I use Goose for commercial analysis?
**A:** Yes! Goose is licensed under Apache 2.0, which allows commercial use. See the [LICENSE](../LICENSE) file for details.

---

## Troubleshooting

### Q: I get "ModuleNotFoundError" when running Goose
**A:** Run `goose doctor --fix` to automatically install missing dependencies.

### Q: Goose says "unsupported log format"
**A:** Goose supports PX4 ULog (.ulg), ArduPilot DataFlash (.bin, .log), and generic CSV (.csv). MAVLink TLog (.tlog) requires Goose Pro. If your file is a supported format and still fails, it may be corrupted or malformed. Check [Supported Formats](supported-formats.md).

### Q: Why is my analysis score different each time I run it?
**A:** This shouldn't happen for the same log file. If it does, you may have changed the configuration or installed a different plugin version. Run `goose doctor` to verify your setup.

### Q: I found a bug or have a feature request
**A:** Open an issue on [GitHub](https://github.com/Goose-Flight/Goose-Core/issues) with:
- Log format and Goose version (`goose --version`)
- Python version (`python --version`)
- Your operating system
- The problematic log file (if shareable)

---

## Hardware & Compatibility

### Q: What PX4 versions does Goose support?
**A:** Goose works with PX4 v1.10 and newer. Newer versions are always better supported due to improved logging.

### Q: Does Goose work with ArduPilot?
**A:** Yes. The ArduPilot DataFlash parser is implemented in Core and provides basic message extraction from `.bin` and `.log` files.

### Q: Can I analyze logs from [my specific hardware]?
**A:** If your hardware runs PX4 (ULog), ArduPilot (DataFlash), or exports CSV telemetry, yes. MAVLink TLog requires Goose Pro. Open a GitHub issue if you need a specific format.

---

## Getting Help

- **Getting started?** → [Getting Started Guide](getting-started.md)
- **Need CLI docs?** → [CLI Reference](cli-reference.md)
- **Want to write a plugin?** → [Writing Plugins](writing-plugins.md)
- **Questions about configuration?** → [Configuration Guide](configuration.md)
- **Have a bug?** → [GitHub Issues](https://github.com/Goose-Flight/Goose-Core/issues)
- **Contributing?** → [Contributing Guide](../CONTRIBUTING.md)
