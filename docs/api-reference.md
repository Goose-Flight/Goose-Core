# REST API Reference

The Goose REST API provides programmatic access to flight forensic features.
Start the server with `goose serve` and interact via HTTP.

The primary workflow is case-oriented: create a case, ingest evidence, run
analysis, and view findings. A backward-compatible `/api/analyze` shim is
preserved for single-file analysis without case management.

**Base URL:** `http://127.0.0.1:8000/api/` (default)

---

## Case API (Primary)

### GET `/api/cases`

List all cases.

### POST `/api/cases`

Create a new forensic case.

### POST `/api/cases/{id}/evidence`

Ingest evidence into a case. The uploaded file is hashed (SHA-256 + SHA-512),
stored immutably in the case evidence directory, and an evidence manifest entry
is written. An audit log entry is recorded.

### POST `/api/cases/{id}/analyze`

Run analysis on the evidence in a case. Plugin findings are stored in the case
analysis directory and an audit log entry is recorded.

### GET `/api/cases/{id}`

Get case details including evidence inventory, analysis runs, and status.

---

## Legacy API (Compatibility)

The following endpoints are preserved for backward compatibility. They operate
without the case system -- uploading a file, analyzing it, and returning results
in a single request.

---

## Health Check

### GET `/api/health`

Check server health and version.

**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

**cURL Example:**
```bash
curl http://127.0.0.1:8000/api/health
```

**Python Example:**
```python
import requests
resp = requests.get("http://127.0.0.1:8000/api/health")
print(resp.json())  # {'status': 'ok', 'version': '1.0.0'}
```

---

## List Plugins

### GET `/api/plugins`

Get all installed analysis plugins.

**Response:**
```json
[
  {
    "name": "vibration",
    "description": "Detect abnormal vibration patterns"
  },
  {
    "name": "battery_sag",
    "description": "Monitor battery voltage sag under load"
  },
  {
    "name": "crash_detection",
    "description": "Detect crashes and impacts"
  }
]
```

**cURL Example:**
```bash
curl http://127.0.0.1:8000/api/plugins
```

**Python Example:**
```python
import requests
resp = requests.get("http://127.0.0.1:8000/api/plugins")
plugins = resp.json()
for plugin in plugins:
    print(f"{plugin['name']}: {plugin['description']}")
```

---

## Analyze Flight

### POST `/api/analyze`

Upload a flight log and run all applicable analysis plugins.

**Request:**
- **Method:** POST (multipart form data)
- **Body:** `file` (binary, required) — Flight log file (`.ulg` only; other formats not yet supported)

**Response:**
```json
{
  "findings": [
    {
      "plugin": "vibration",
      "title": "High Vibration Detected",
      "severity": "warning",
      "score": 45,
      "description": "Vibration levels exceed normal range.",
      "evidence": {
        "frequency_hz": 32.5,
        "amplitude_g": 1.2
      },
      "phase": "climb",
      "timestamp_start": 10.5,
      "timestamp_end": 45.3
    }
  ],
  "plugins_run": ["vibration", "battery_sag", "crash_detection", "gps_check", ...],
  "file_name": "flight.ulg"
}
```

**Field Descriptions:**

| Field | Type | Description |
| --- | --- | --- |
| `findings` | array | List of analysis findings from all plugins |
| `findings[].plugin` | string | Name of the plugin that generated this finding |
| `findings[].title` | string | Short title of the finding |
| `findings[].severity` | string | `critical`, `warning`, `info`, or `pass` |
| `findings[].score` | number | Plugin score 0-100 (higher is better) |
| `findings[].description` | string | Detailed description of the finding |
| `findings[].evidence` | object | Supporting evidence data (varies by plugin) |
| `findings[].phase` | string | Flight phase where finding occurred (optional) |
| `findings[].timestamp_start` | number | Start time in seconds (optional) |
| `findings[].timestamp_end` | number | End time in seconds (optional) |
| `plugins_run` | array | List of all plugins that ran |
| `file_name` | string | Original filename of the uploaded file |

**cURL Example:**
```bash
curl -X POST -F "file=@flight.ulg" \
  http://127.0.0.1:8000/api/analyze
```

**Python Example:**
```python
import requests
import json

with open("flight.ulg", "rb") as f:
    files = {"file": f}
    resp = requests.post("http://127.0.0.1:8000/api/analyze", files=files)

analysis = resp.json()
print(f"Analyzed: {analysis['file_name']}")
print(f"Found {len(analysis['findings'])} findings")

for finding in analysis['findings']:
    print(f"  [{finding['severity']}] {finding['plugin']}: {finding['title']}")
```

**JavaScript Example:**
```javascript
const formData = new FormData();
formData.append("file", fileInput.files[0]);

const response = await fetch("http://127.0.0.1:8000/api/analyze", {
  method: "POST",
  body: formData,
});

const analysis = await response.json();
console.log(`Found ${analysis.findings.length} findings`);
```

---

## Detect Crash

### POST `/api/crash`

Upload a flight log and get crash detection with root cause analysis.

**Request:**
- **Method:** POST (multipart form data)
- **Body:** `file` (binary, required) — Flight log file (`.ulg` only; other formats not yet supported)

**Response:**
```json
{
  "crashed": true,
  "confidence": 0.87,
  "classification": "motor_failure",
  "root_cause": "Motor 3 output dropped to zero at t=261s.",
  "evidence_chain": [
    "Motor 3 output fell below threshold",
    "Attitude divergence exceeded limits",
    "Descent rate exceeded safety threshold"
  ],
  "contributing_factors": [
    "High vibration prior to failure",
    "Motor bearing wear detected"
  ],
  "inspect_checklist": [
    "Check motor 3 bearings and shaft play",
    "Inspect ESC solder joints",
    "Verify wiring harness integrity"
  ],
  "timeline": [
    {
      "timestamp": 258,
      "event": "Motor 3 output dropped",
      "severity": "critical"
    },
    {
      "timestamp": 261,
      "event": "High-g impact detected",
      "severity": "critical"
    }
  ]
}
```

**Field Descriptions:**

| Field | Type | Description |
| --- | --- | --- |
| `crashed` | boolean | True if crash was detected |
| `confidence` | number | Crash confidence 0.0-1.0 (0-100%) |
| `classification` | string | Crash type: `motor_failure`, `power_loss`, `gps_loss`, `pilot_error`, `mechanical`, `unknown` |
| `root_cause` | string | One-line explanation of most likely failure |
| `evidence_chain` | array | Ordered list of supporting evidence |
| `contributing_factors` | array | Other factors that contributed to crash |
| `inspect_checklist` | array | Physical inspection items |
| `timeline` | array | Chronological events (each has `timestamp`, `event`, `severity`) |

**cURL Example:**
```bash
curl -X POST -F "file=@flight.ulg" \
  http://127.0.0.1:8000/api/crash
```

**Python Example:**
```python
import requests

with open("flight.ulg", "rb") as f:
    files = {"file": f}
    resp = requests.post("http://127.0.0.1:8000/api/crash", files=files)

crash = resp.json()

if crash["crashed"]:
    print(f"🔴 CRASH DETECTED ({crash['confidence']*100:.0f}% confidence)")
    print(f"Type: {crash['classification']}")
    print(f"Cause: {crash['root_cause']}")
    print("\nInspect:")
    for item in crash["inspect_checklist"]:
        print(f"  ☐ {item}")
else:
    print("✓ No crash detected")
```

**JavaScript Example:**
```javascript
const formData = new FormData();
formData.append("file", fileInput.files[0]);

const response = await fetch("http://127.0.0.1:8000/api/crash", {
  method: "POST",
  body: formData,
});

const crash = await response.json();

if (crash.crashed) {
  console.log(`Crash detected: ${crash.classification}`);
  console.log(`Confidence: ${(crash.confidence * 100).toFixed(0)}%`);
  console.log(`Cause: ${crash.root_cause}`);
} else {
  console.log("No crash detected");
}
```

---

## Error Responses

The API returns appropriate HTTP status codes and error details.

### 400 Bad Request

Missing or invalid file.

```json
{
  "detail": "No file provided"
}
```

### 422 Unprocessable Entity

Invalid file format or parsing error.

```json
{
  "detail": "Failed to parse flight.ulg: Invalid ULog format"
}
```

### 500 Internal Server Error

Server error during processing.

```json
{
  "detail": "Internal server error"
}
```

---

## Integration Examples

### Batch Analysis Script

```python
import requests
from pathlib import Path
import json

API_URL = "http://127.0.0.1:8000/api"
LOG_DIR = Path("logs")
REPORT_DIR = Path("reports")

REPORT_DIR.mkdir(exist_ok=True)

for log_file in LOG_DIR.glob("*.ulg"):
    print(f"Analyzing {log_file.name}...", end=" ")
    
    with open(log_file, "rb") as f:
        resp = requests.post(f"{API_URL}/crash", files={"file": f})
    
    crash = resp.json()
    report = {
        "file": log_file.name,
        "crashed": crash["crashed"],
        "confidence": crash["confidence"],
        "classification": crash["classification"],
    }
    
    report_file = REPORT_DIR / f"{log_file.stem}_report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"{'CRASHED' if crash['crashed'] else 'OK'}")
```

### Real-time Dashboard Integration

```javascript
// Monitor a folder and display analysis results in real-time
const API_URL = "http://127.0.0.1:8000/api";

async function analyzeLog(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(`${API_URL}/analyze`, {
      method: "POST",
      body: formData,
    });

    const analysis = await response.json();

    // Group findings by severity
    const bySeverity = {
      critical: [],
      warning: [],
      info: [],
      pass: [],
    };

    analysis.findings.forEach((finding) => {
      bySeverity[finding.severity].push(finding);
    });

    return {
      file: analysis.file_name,
      findings: bySeverity,
      totalPlugins: analysis.plugins_run.length,
    };
  } catch (error) {
    console.error("API error:", error);
    return null;
  }
}
```

---

## Rate Limits & Performance

- **File size limit:** 500 MB (typical logs are 1-50 MB)
- **Timeout:** 60 seconds per request
- **Concurrency:** Limited by server resources; one analysis at a time recommended for stability

---

## Authentication & Security

The API has **no authentication** by default. Deploy behind a reverse proxy (nginx, Apache) or API gateway for production use.

**Never expose the API to untrusted networks** unless you add authentication/authorization.

---

## API Status & Changes

The case-oriented API (`/api/cases` family) is the primary interface as of
Sprint 2. The legacy `/api/analyze` and `/api/crash` endpoints are preserved as
backward-compatible shims. The API may evolve as new sprints are completed.

