# Troubleshooting Guide

## Installation Issues

### ModuleNotFoundError: No module named 'goose'

**Symptom:** `goose` command not found or `from goose import ...` fails

**Solutions:**
1. Install or reinstall: `pip install goose-flight`
2. If you edited the source, reinstall in development mode: `pip install -e .`
3. Verify: `python -c "import goose; print(goose.__version__)"`
4. Use the automated fixer: `goose doctor --fix`

### pip install fails with "No matching distribution found"

**Symptom:** `ERROR: Could not find a version that satisfies the requirement goose-flight`

**Solutions:**
1. Upgrade pip: `pip install --upgrade pip`
2. Check Python version: `python --version` (must be 3.10+)
3. Try installing with `--no-cache-dir`: `pip install --no-cache-dir goose-flight`
4. Check your internet connection and try again

### ImportError on Windows

**Symptom:** DLL/dependency errors on Windows startup

**Solutions:**
1. Ensure Python is installed for "all users" (not just current user)
2. Run `goose doctor --fix` to auto-install missing packages
3. Try updating: `pip install --upgrade goose-flight`
4. Check that your Windows Defender or antivirus isn't blocking the package

---

## Runtime Issues

### "unsupported log file format" or "unable to parse log"

**Symptom:** Goose doesn't recognize your log file

**Causes & Solutions:**

| Symptom | Likely Cause | Solution |
| --- | --- | --- |
| `.ulg` file won't parse | Corrupted ULog | Verify file integrity: `hexdump -C file.ulg \| head` should show "ULG" magic bytes |
| `.bin` or `.log` won't parse | Format not yet supported | ArduPilot DataFlash parser is not yet implemented. Only PX4 ULog (.ulg) is currently supported. |
| `.tlog` won't parse | Format not yet supported | MAVLink TLog parser is not yet implemented. Only PX4 ULog (.ulg) is currently supported. |
| CSV file won't parse | Format not yet supported | CSV parser is not yet implemented. Only PX4 ULog (.ulg) is currently supported. |

**Verify a log file:**
```bash
# Check if it's a valid ULog (starts with "ULG" magic bytes)
file flight.ulg

# Try to analyze it
goose crash flight.ulg

# Get details on the parser
goose plugins info ulog_parser
```

### Crash analysis takes too long or hangs

**Symptom:** `goose crash` or `goose analyze` seems stuck or very slow

**Solutions:**
1. Check file size: Large logs (>1GB) may take longer. This is normal.
2. Interrupt and try: `goose analyze flight.ulg --plugin crash_detection` (fewer plugins = faster)
3. Check system resources: Is your CPU/RAM heavily used? Close other apps.
4. Enable verbose output for debugging: `goose crash flight.ulg -v` to see progress
5. Check the plugin timeout: if one plugin is hanging, try running others: `goose plugins list`

### "No data available" or missing analysis results

**Symptom:** Plugin returns no findings or "N/A"

**Causes & Solutions:**

- **Missing log fields:** The log doesn't contain the data the plugin needs. Example: GPS plugin requires GPS data.
  - Solution: Verify the log was recorded with all sensors active.
  
- **Minimal log data:** Very short flights may not have enough data for analysis.
  - Solution: Analyze longer flights (>30 seconds recommended).

- **Wrong sensor calibration:** Sensors may have been misconfigured.
  - Solution: Check your flight controller calibration and re-record a test flight.

---

## Plugin Issues

### Plugin not found or not loading

**Symptom:** `goose plugins list` shows fewer plugins than expected

**Solutions:**
1. Reinstall: `pip install --upgrade goose-flight`
2. Check Python version: plugins require Python 3.10+
3. Run the fixer: `goose doctor --fix`
4. Check for import errors:
   ```bash
   python -c "from goose.plugins import *"
   ```

### Plugin analysis results seem wrong

**Symptom:** Plugin score seems too high/low, or findings don't make sense

**Causes & Solutions:**

1. **Configuration mismatch:** Your thresholds may not match your aircraft.
   - Solution: Check [Configuration](configuration.md) and adjust thresholds.

2. **Different sensor setup:** Plugin was designed for different hardware.
   - Solution: Review the plugin description with `goose plugins info vibration` (or whichever plugin).

3. **Log data quality:** Sensor noise or dropouts may cause false findings.
   - Solution: Check sensor calibration. Verify with a known-good log.

4. **Plugin version mismatch:** You may be running an older plugin version.
   - Solution: `goose doctor --fix` and `pip install --upgrade goose-flight`.

---

## Output & Export Issues

### JSON output is invalid or incomplete

**Symptom:** `goose crash -f json` produces invalid JSON

**Solutions:**
1. Verify the output isn't truncated: check file size with `ls -lh report.json`
2. Try with verbose: `goose crash flight.ulg -f json -v > report.json 2>&1`
3. Parse the JSON to find the issue: `python -m json.tool report.json | head`
4. Try with a simpler log file first: `goose crash test.ulg -f json`

### Text report is hard to read on terminal

**Symptom:** Colors are wrong, output is garbled, or unreadable

**Solutions:**
1. Disable colors: `goose crash flight.ulg --no-color`
2. Pipe to a file and view: `goose crash flight.ulg > report.txt && cat report.txt`
3. Check terminal encoding: `echo $LANG` (should include `utf-8`)
4. Try a different terminal/emulator

### Can't export to PDF or HTML

**Symptom:** Goose doesn't have `--pdf` or `--html` options

**Solution:** Export as JSON or text, then convert with external tools:
```bash
# Text to PDF (requires pandoc)
goose crash flight.ulg -o report.txt
pandoc report.txt -o report.pdf

# JSON to custom HTML (write your own script, or use jq + a template)
goose crash flight.ulg -f json | jq . > report.json
```

---

## Web Interface Issues

### `goose serve` won't start or won't connect

**Symptom:** Connection refused, port already in use, or UI won't load

**Solutions:**
1. Check if port 8000 is free: `netstat -an | grep 8000` (or use a different port)
2. Start on a different port: `goose serve -p 9000`
3. Bind to localhost only: `goose serve -h 127.0.0.1 -p 8000`
4. Check if another service is using the port: `lsof -i :8000` (macOS/Linux)
5. Verify the API is running: `curl http://127.0.0.1:8000/api/health`

### Web UI shows "Loading..." forever

**Symptom:** The dashboard page never loads or stays blank

**Solutions:**
1. Check browser console for errors: Open DevTools (F12)
2. Check the API: `curl http://127.0.0.1:8000/api/health` should return `{"status":"ok"}`
3. Try a different browser
4. Clear browser cache: Ctrl+Shift+Del (or Cmd+Shift+Del on macOS)
5. Restart the server: Ctrl+C then `goose serve`

### CORS errors or API request failures

**Symptom:** Browser console shows "CORS error" or "preflight request failed"

**Solutions:**
1. Ensure the API is running: `goose serve`
2. Check that API URL is correct in the browser (should be `http://127.0.0.1:8000`)
3. The API is in development — try the CLI instead: `goose crash flight.ulg`

---

## Data Privacy & Security

### Is my data secure? Will Goose upload my logs?

**Answer:** Goose is completely local and air-gapped.
- ✓ No network calls, ever
- ✓ Logs stay on your computer
- ✓ Open source — audit the code yourself

---

## Getting More Help

1. **Check the docs:** [Getting Started](getting-started.md), [CLI Reference](cli-reference.md), [FAQ](faq.md)
2. **Verify your setup:** `goose doctor`
3. **Search existing issues:** [GitHub Issues](https://github.com/Goose-Flight/Goose-Core/issues)
4. **Open a new issue** with:
   - `goose --version`
   - `python --version`
   - Your OS (Linux/macOS/Windows)
   - The exact command you ran
   - The full error message
   - Your log file (if shareable) or a minimal reproduction case

