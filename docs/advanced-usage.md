# Advanced Usage

Beyond basic analysis, Goose can be integrated into automation workflows, batch processing pipelines, and custom applications.

---

## Batch Analysis

### Process Multiple Log Files

```bash
# Analyze all .ulg files in a directory
for file in logs/*.ulg; do
  goose crash "$file" -o "reports/$(basename "$file" .ulg).txt"
done
```

### Export All Results to JSON

```bash
# Batch export to JSON for processing
for file in logs/*.ulg; do
  goose crash "$file" -f json -o "reports/$(basename "$file" .ulg).json"
done
```

### Parallel Analysis (GNU Parallel)

For faster processing of many files:

```bash
# Analyze 4 files in parallel
find logs -name "*.ulg" | parallel -j 4 "goose crash {} -o reports/{/.}.json -f json"
```

### Batch Analysis with Python

```python
from pathlib import Path
import subprocess
import json

log_dir = Path("flight_logs")
report_dir = Path("analysis_reports")
report_dir.mkdir(exist_ok=True)

for log_file in log_dir.glob("*.ulg"):
    print(f"Processing {log_file.name}...")
    
    result = subprocess.run(
        ["goose", "crash", str(log_file), "-f", "json"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0:
        data = json.loads(result.stdout)
        
        # Save report
        report_file = report_dir / f"{log_file.stem}_report.json"
        with open(report_file, "w") as f:
            json.dump(data, f, indent=2)
        
        # Summary
        print(f"  Crashed: {data['crashed']}")
        print(f"  Confidence: {data['confidence']*100:.0f}%")
    else:
        print(f"  Error: {result.stderr}")
```

---

## Integration with Custom Scripts

### Extract Specific Plugin Results

```bash
# Get only vibration plugin score
goose crash flight.ulg -f json | python3 -c "
import json, sys
data = json.load(sys.stdin)
vibration = next(f for f in data['findings'] if f['plugin'] == 'vibration')
print(f'Vibration score: {vibration[\"score\"]}/100')
"
```

### Filter Crashes Above Confidence Threshold

```python
import json
import subprocess

def analyze_with_threshold(log_file, min_confidence=0.75):
    result = subprocess.run(
        ["goose", "crash", log_file, "-f", "json"],
        capture_output=True,
        text=True,
    )
    
    data = json.loads(result.stdout)
    
    if data["crashed"] and data["confidence"] >= min_confidence:
        return {
            "file": log_file,
            "classification": data["classification"],
            "confidence": data["confidence"],
            "root_cause": data["root_cause"],
        }
    
    return None

# Analyze logs and filter high-confidence crashes
for log in Path("logs").glob("*.ulg"):
    crash = analyze_with_threshold(str(log), min_confidence=0.8)
    if crash:
        print(f"HIGH CONFIDENCE CRASH: {crash}")
```

### Generate Custom Reports

```python
import json
import subprocess
from jinja2 import Template

# Template for custom HTML report
REPORT_TEMPLATE = """
<html>
<head><title>Crash Analysis Report</title></head>
<body>
  <h1>{{ file_name }}</h1>
  
  {% if crashed %}
    <h2 style="color: red;">🔴 CRASH DETECTED</h2>
    <p><strong>Confidence:</strong> {{ confidence*100 }}%</p>
    <p><strong>Type:</strong> {{ classification }}</p>
    <p><strong>Root Cause:</strong> {{ root_cause }}</p>
  {% else %}
    <h2 style="color: green;">✓ No Crash</h2>
  {% endif %}
  
  <h3>Findings</h3>
  <table border="1">
    <tr><th>Plugin</th><th>Severity</th><th>Score</th><th>Title</th></tr>
    {% for finding in findings %}
      <tr>
        <td>{{ finding.plugin }}</td>
        <td>{{ finding.severity }}</td>
        <td>{{ finding.score }}/100</td>
        <td>{{ finding.title }}</td>
      </tr>
    {% endfor %}
  </table>
</body>
</html>
"""

def generate_html_report(log_file, output_file):
    # Run analysis
    result = subprocess.run(
        ["goose", "crash", log_file, "-f", "json"],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    
    # Render template
    template = Template(REPORT_TEMPLATE)
    html = template.render(
        file_name=data["file"],
        crashed=data["crashed"],
        confidence=data["confidence"],
        classification=data["classification"],
        root_cause=data["root_cause"],
        findings=data["findings"],
    )
    
    # Save
    with open(output_file, "w") as f:
        f.write(html)

generate_html_report("flight.ulg", "report.html")
```

---

## Embedded Usage (Python Library)

Import Goose as a library in your own Python code:

```python
from goose.core import Flight
from goose.parsers.ulog import ULogParser
from goose.plugins.registry import load_plugins
from goose.core.crash_detector import analyze_crash

# Parse a log file
parser = ULogParser()
flight = parser.parse("flight.ulg")

# Run all plugins
plugins = load_plugins()
findings = []

for plugin in plugins:
    if plugin.applicable(flight):
        findings.extend(plugin.analyze(flight, config={}))

# Analyze crash
crash = analyze_crash(flight, findings)

print(f"Crashed: {crash.crashed}")
print(f"Confidence: {crash.confidence:.0%}")
print(f"Cause: {crash.root_cause}")
```

---

## REST API Integration

Use the `goose serve` command to expose a REST API:

```bash
# Start the server
goose serve -p 8000

# In another terminal, use the API
curl -X POST -F "file=@flight.ulg" http://127.0.0.1:8000/api/crash
```

See [API Reference](api-reference.md) for complete endpoint documentation.

---

## Configuration Customization

### Override Plugin Thresholds

Create a `goose.yaml` file to customize plugin behavior:

```yaml
plugins:
  vibration:
    threshold_hz: 35
    max_amplitude_g: 1.5
  battery_sag:
    min_voltage: 9.5
    warning_threshold: 10.0
  crash_detection:
    impact_threshold_g: 3.5
```

Then run analysis with custom config:

```bash
goose crash flight.ulg  # Uses goose.yaml if present
```

See [Configuration](configuration.md) for all available parameters.

---

## Performance Optimization

### Analyzing Large Log Files

For very large logs (>100 MB), consider:

1. **Run specific plugins only:**
   ```bash
   goose analyze flight.ulg --plugin vibration --plugin crash_detection
   ```

2. **Use analysis mode instead of crash mode:**
   ```bash
   # Crash mode does extra synthesis work
   goose analyze flight.ulg  # Just raw plugin results
   ```

3. **Increase timeout for long analysis:**
   ```bash
   timeout 300 goose crash very_large_flight.ulg
   ```

### Memory Usage

Goose loads entire log files into memory. For very large files:

- Use a machine with adequate RAM (8+ GB recommended for 500+ MB files)
- Process files sequentially rather than in parallel
- Consider downsampling very large logs if possible

---

## Monitoring & Automation

### Automated Flight Analysis Pipeline

```python
"""Example: Monitor a directory and auto-analyze new logs."""
import time
from pathlib import Path
import subprocess
import json

WATCH_DIR = Path("raw_logs")
PROCESS_DIR = Path("analyzed")
ARCHIVE_DIR = Path("archive")

def process_new_logs():
    while True:
        for log_file in WATCH_DIR.glob("*.ulg"):
            print(f"Found: {log_file.name}")
            
            # Analyze
            result = subprocess.run(
                ["goose", "crash", str(log_file), "-f", "json"],
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                # Save result
                report_file = PROCESS_DIR / f"{log_file.stem}_report.json"
                with open(report_file, "w") as f:
                    json.dump(data, f, indent=2)
                
                # Archive original
                log_file.rename(ARCHIVE_DIR / log_file.name)
                
                # Alert if crash detected
                if data["crashed"] and data["confidence"] > 0.8:
                    print(f"⚠️  HIGH-CONFIDENCE CRASH: {data['classification']}")
                    # Could send alert, email, webhook, etc.
            else:
                print(f"❌ Error processing {log_file.name}")
                log_file.rename(ARCHIVE_DIR / f"error_{log_file.name}")
        
        time.sleep(10)  # Check every 10 seconds

if __name__ == "__main__":
    WATCH_DIR.mkdir(exist_ok=True)
    PROCESS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    
    process_new_logs()
```

### Webhook Alerting

```python
"""Send crash alerts via webhook."""
import requests
import json
import subprocess

WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

def analyze_and_alert(log_file):
    result = subprocess.run(
        ["goose", "crash", log_file, "-f", "json"],
        capture_output=True,
        text=True,
    )
    
    data = json.loads(result.stdout)
    
    if data["crashed"] and data["confidence"] > 0.7:
        message = {
            "text": f"🔴 Crash Detected: {data['classification']}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{data['root_cause']}*\nConfidence: {data['confidence']*100:.0f}%",
                    },
                }
            ],
        }
        
        requests.post(WEBHOOK_URL, json=message)
```

---

## Troubleshooting Advanced Usage

- **Large files hang:** Check system memory and disk space
- **Plugin conflicts:** Ensure compatible plugin versions with `goose doctor`
- **API timeouts:** Increase timeout in your HTTP client or reduce file size
- **Custom config not applied:** Verify `goose.yaml` location and format

For additional help, see [Troubleshooting](troubleshooting.md).

