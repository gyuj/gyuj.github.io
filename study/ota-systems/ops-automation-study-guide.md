# Operations & AI Automation Engineer — Study Guide

> Prep guide tailored to the actual role: investigating operational issues, log analysis, AI-driven automation, scripting, and building tools for OTA/connected vehicle operations.

---

# Table of Contents

1. [Module 1: Root-Cause Analysis & Troubleshooting](#module-1-root-cause-analysis--troubleshooting)
2. [Module 2: Log Analysis & System Monitoring](#module-2-log-analysis--system-monitoring)
3. [Module 3: Python Scripting for Operations](#module-3-python-scripting-for-operations)
4. [Module 4: AI Tools for Automation & Productivity](#module-4-ai-tools-for-automation--productivity)
5. [Module 5: APIs, Databases & Integration](#module-5-apis-databases--integration)
6. [Module 6: Linux & Cloud Fundamentals](#module-6-linux--cloud-fundamentals)
7. [Module 7: Monitoring, Reporting & Dashboards](#module-7-monitoring-reporting--dashboards)
8. [Module 8: Connected Devices & OTA Operations Context](#module-8-connected-devices--ota-operations-context)
9. [Resources & Study Schedule](#resources--study-schedule)

---

# Module 1: Root-Cause Analysis & Troubleshooting

This is the core of the role — you'll be investigating why things broke and figuring out how to fix them.

## 1.1 The RCA Process

Root-cause analysis (RCA) is a structured approach to finding the *underlying* cause of a problem, not just the symptoms.

```
INCIDENT: "50 vehicles failed to update last night"

      Symptom
         │
         ▼
  ┌──────────────┐
  │ What happened?│  ← Timeline reconstruction
  └──────┬───────┘
         │
  ┌──────────────┐
  │ Where?        │  ← Scope (which vehicles, regions, versions)
  └──────┬───────┘
         │
  ┌──────────────┐
  │ When did it   │  ← Correlate with deployments, config changes
  │ start/stop?   │
  └──────┬───────┘
         │
  ┌──────────────┐
  │ Why?          │  ← The "5 Whys" — keep asking until you hit root cause
  └──────┬───────┘
         │
      Root Cause
         │
         ▼
      Fix + Prevention
```

### The 5 Whys Technique

```
Problem: 50 vehicles failed OTA update

Why 1: The download timed out
Why 2: The CDN returned 503 errors
Why 3: The CDN cache was invalidated during the rollout
Why 4: A config change was pushed to CDN during peak update window
Why 5: There's no change freeze policy during active campaigns

Root cause: Missing operational policy for change freezes during rollouts
Fix: Implement change freeze windows + automated checks
```

### Fishbone (Ishikawa) Diagram

Categorize potential causes to avoid tunnel vision:

```
        People          Process          Technology
          │                │                │
          ├─ Misconfigured ├─ No change     ├─ CDN cache bug
          │   by operator  │   freeze policy│
          ├─ Understaffed  ├─ No rollback   ├─ Timeout too short
          │   night shift  │   automation   │
          │                │                │
          └────────────────┴────────────────┘
                           │
                    ┌──────┴──────┐
                    │  UPDATE     │
                    │  FAILURE    │
                    └─────────────┘
                           │
          ┌────────────────┴────────────────┐
          │                │                │
        Environment     Data             External
          │                │                │
          ├─ Network       ├─ Corrupt       ├─ Cellular carrier
          │   congestion   │   metadata     │   outage
          ├─ Region-       ├─ Wrong version ├─ Third-party CDN
          │   specific     │   targeting    │   issue
```

### Incident Response Template

When investigating an issue, structure your notes like this:

```markdown
## Incident Report: [Brief title]

**Date/Time**: 2026-09-20 02:30 UTC
**Severity**: P2
**Duration**: 4 hours
**Impact**: 50 vehicles failed OTA update in NA region

### Timeline
- 02:30 — Monitoring alert: update failure rate > 5%
- 02:45 — On-call engineer begins investigation
- 03:00 — Identified: CDN returning 503 for package URLs
- 03:15 — CDN team confirms unplanned cache invalidation
- 03:30 — CDN cache manually restored
- 04:00 — Failure rate returns to normal
- 06:30 — All affected vehicles retried and updated successfully

### Root Cause
CDN configuration change deployed during active OTA campaign triggered
full cache invalidation. No change freeze policy was in place.

### Action Items
- [ ] Implement change freeze windows during active campaigns
- [ ] Add CDN health check to campaign pre-flight validation
- [ ] Create runbook for CDN-related update failures
```

## 1.2 Debugging Strategies

### Binary Search Debugging

When you don't know where the problem is, narrow down by halves:

```
Full pipeline: Ingest → Process → Package → Distribute → Download → Install → Verify

Step 1: Does the package exist on CDN?
  YES → problem is downstream (Download → Install → Verify)
  NO  → problem is upstream (Ingest → Process → Package → Distribute)

Step 2: Does the vehicle initiate download?
  YES → problem is Install or Verify
  NO  → problem is Download (connectivity, DNS, auth)

Step 3: ...keep halving until you isolate the failing component
```

### Correlation Analysis

When investigating patterns in failures:

```python
# "Which vehicles failed? Do they share anything in common?"
import pandas as pd

failures = pd.read_csv("update_failures.csv")

# Group by attributes to find patterns
print(failures.groupby("vehicle_model").size())
print(failures.groupby("region").size())
print(failures.groupby("sw_version").size())
print(failures.groupby("cellular_carrier").size())

# If 90% of failures are on one carrier in one region → network issue
# If 90% are one model → hardware/firmware compatibility issue
# If 90% are one sw_version → version-specific bug
```

## 1.3 Common Operational Issues in OTA / Connected Platforms

| Category | Example Issues |
|----------|---------------|
| **Connectivity** | Timeouts, DNS failures, certificate expiry, carrier throttling |
| **Configuration** | Wrong targeting (sent update to wrong vehicles), invalid campaign params |
| **Capacity** | CDN overloaded, database connection pool exhausted, S3 rate limits |
| **Compatibility** | Package incompatible with hardware revision, dependency conflict |
| **Process** | Manual error, missed approval step, change during freeze window |
| **Data** | Corrupt metadata, stale vehicle registry, duplicate records |

---

# Module 2: Log Analysis & System Monitoring

## 2.1 Log Fundamentals

Logs are your primary tool for investigation. You need to read them fast and extract signal from noise.

### Log Levels

```
TRACE   — Extremely detailed, step-by-step execution (rarely enabled in prod)
DEBUG   — Detailed diagnostic info for developers
INFO    — Normal operational events ("Update started", "Download complete")
WARNING — Something unexpected but not broken ("Retry attempt 2/3")
ERROR   — Something failed ("Download failed: connection timeout")
FATAL   — System cannot continue ("Out of memory, shutting down")
```

**In practice**: Production systems usually log at INFO level. When investigating, you may temporarily enable DEBUG on specific components.

### Structured Logging

Modern systems use JSON-structured logs instead of plain text:

```json
{
  "timestamp": "2026-09-20T02:30:15.123Z",
  "level": "ERROR",
  "service": "ota-download-service",
  "message": "Package download failed",
  "vehicle_id": "VIN12345",
  "campaign_id": "camp-2026-09-20",
  "package_id": "fw-2.1.0",
  "error": "ConnectionTimeout",
  "retry_count": 3,
  "duration_ms": 30000,
  "region": "us-west-2"
}
```

**Why structured?** You can query, filter, aggregate. "Show me all ERROR logs for campaign X where retry_count >= 3" is trivial with structured logs, impossible to reliably do with grep on plain text.

## 2.2 Log Analysis with Command Line

### Essential Commands

```bash
# Search for errors in a log file
grep "ERROR" app.log

# Search with context (3 lines before and after)
grep -B 3 -A 3 "ConnectionTimeout" app.log

# Count errors by type
grep "ERROR" app.log | grep -oP '"error": "\K[^"]+' | sort | uniq -c | sort -rn

# Filter by time range (logs with timestamps)
awk '$0 >= "2026-09-20T02:00" && $0 <= "2026-09-20T03:00"' app.log

# Follow a log in real-time
tail -f app.log | grep --line-buffered "ERROR"

# Parse JSON logs with jq
cat app.log | jq -r 'select(.level == "ERROR") | [.timestamp, .service, .message] | @tsv'

# Top 10 most common errors
cat app.log | jq -r 'select(.level == "ERROR") | .message' | sort | uniq -c | sort -rn | head -10

# Find all unique vehicle IDs that hit errors
cat app.log | jq -r 'select(.level == "ERROR") | .vehicle_id' | sort -u

# Timeline of errors (count per minute)
cat app.log | jq -r 'select(.level == "ERROR") | .timestamp[:16]' | sort | uniq -c
```

### jq — Your Best Friend for JSON Logs

```bash
# Pretty-print a JSON log entry
echo '{"level":"ERROR","msg":"timeout"}' | jq .

# Filter by field value
cat logs.json | jq 'select(.service == "download-svc")'

# Extract specific fields
cat logs.json | jq '{time: .timestamp, error: .message, vin: .vehicle_id}'

# Count by field
cat logs.json | jq -r '.region' | sort | uniq -c

# Complex filter: errors in us-west with retry > 2
cat logs.json | jq 'select(.level == "ERROR" and .region == "us-west-2" and .retry_count > 2)'
```

## 2.3 Log Analysis with Python

For deeper analysis, load logs into pandas:

```python
import json
import pandas as pd

# Load JSON logs
logs = []
with open("app.log") as f:
    for line in f:
        try:
            logs.append(json.loads(line))
        except json.JSONDecodeError:
            continue

df = pd.DataFrame(logs)
df["timestamp"] = pd.to_datetime(df["timestamp"])

# Error rate over time
errors = df[df["level"] == "ERROR"]
error_rate = errors.set_index("timestamp").resample("5min").size()
print(error_rate)

# Top errors by service
print(errors.groupby(["service", "message"]).size().sort_values(ascending=False).head(20))

# Find correlations
# Do failures correlate with a specific region?
print(pd.crosstab(errors["region"], errors["message"]))

# Average response time by service
print(df.groupby("service")["duration_ms"].describe())

# Identify outliers
p99 = df["duration_ms"].quantile(0.99)
slow_requests = df[df["duration_ms"] > p99]
print(f"P99 latency: {p99}ms")
print(f"Slow requests: {len(slow_requests)}")
```

## 2.4 Performance Metrics

Key metrics you'll monitor in an operational role:

### The Four Golden Signals (from Google SRE)

```
┌──────────────────────────────────────────────────┐
│             FOUR GOLDEN SIGNALS                   │
│                                                   │
│  1. LATENCY                                       │
│     How long requests take                        │
│     Track: p50, p95, p99                          │
│     Alert: p99 > 5s                               │
│                                                   │
│  2. TRAFFIC                                       │
│     Request volume (req/sec)                      │
│     Track: by endpoint, by region                 │
│     Alert: sudden spike or drop                   │
│                                                   │
│  3. ERRORS                                        │
│     Failure rate (%)                              │
│     Track: by error type, by service              │
│     Alert: error rate > 1%                        │
│                                                   │
│  4. SATURATION                                    │
│     Resource utilization                          │
│     Track: CPU, memory, disk, connections         │
│     Alert: > 80% utilization                      │
└──────────────────────────────────────────────────┘
```

### OTA-Specific Metrics

| Metric | What It Tells You |
|--------|-------------------|
| Update success rate | % of vehicles that successfully updated |
| Download failure rate | Network/CDN issues |
| Average download time | CDN performance, package size impact |
| Install failure rate | Package compatibility, vehicle-side issues |
| Rollback rate | Update quality — high rollback = bad update |
| Campaign completion time | How long to reach all targeted vehicles |
| Vehicle check-in rate | Fleet connectivity health |
| Time to first update | How quickly vehicles pick up new campaigns |

---

# Module 3: Python Scripting for Operations

## 3.1 Automation Mindset

The rule of thumb: **if you do it more than twice, script it.**

```
Manual task               →  Automation opportunity
─────────────────────────────────────────────────────
Check update status daily →  Scheduled status report script
SSH into 5 servers to     →  Parallel SSH script with
  check logs                  summary output
Generate weekly report    →  Cron job that queries DB,
  in spreadsheet              generates report, emails team
Restart stuck service     →  Health check + auto-restart
  when alert fires            script
```

## 3.2 Essential Python Patterns for Ops

### Script Template

```python
#!/usr/bin/env python3
"""
Script: check_update_status.py
Purpose: Check OTA update campaign status and alert on failures.
Usage: python check_update_status.py --campaign-id CAMP-123
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Check OTA campaign status")
    parser.add_argument("--campaign-id", required=True, help="Campaign ID to check")
    parser.add_argument("--threshold", type=float, default=0.01,
                        help="Failure rate threshold for alerting (default: 1%%)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Checking campaign: {args.campaign_id}")

    try:
        status = get_campaign_status(args.campaign_id)
        failure_rate = status["failed"] / status["total"]

        if failure_rate > args.threshold:
            logger.warning(f"ALERT: Failure rate {failure_rate:.2%} exceeds threshold")
            send_alert(args.campaign_id, failure_rate)
            sys.exit(1)
        else:
            logger.info(f"Campaign healthy. Success: {status['success']}/{status['total']}")

    except Exception as e:
        logger.error(f"Failed to check status: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
```

### Working with APIs

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session():
    """Create a requests session with retry logic."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session

def get_campaign_status(campaign_id):
    """Fetch campaign status from the OTA API."""
    session = create_session()
    response = session.get(
        f"https://ota-api.internal.company.com/v1/campaigns/{campaign_id}/status",
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=30
    )
    response.raise_for_status()
    return response.json()
```

### Processing CSV / Excel Data

```python
import pandas as pd

# Read vehicle fleet data
fleet = pd.read_csv("fleet_inventory.csv")

# Find vehicles that haven't checked in for 7 days
fleet["last_checkin"] = pd.to_datetime(fleet["last_checkin"])
stale = fleet[fleet["last_checkin"] < pd.Timestamp.now() - pd.Timedelta(days=7)]
print(f"Stale vehicles: {len(stale)}")

# Export report
stale.to_excel("stale_vehicles_report.xlsx", index=False)

# Pivot table: update status by model and region
pivot = pd.pivot_table(
    fleet,
    values="vin",
    index="model",
    columns="update_status",
    aggfunc="count",
    fill_value=0
)
print(pivot)
```

### Sending Alerts (Slack / Email)

```python
import requests

def send_slack_alert(webhook_url, message, severity="warning"):
    """Send an alert to Slack."""
    color = {"info": "#36a64f", "warning": "#ff9900", "critical": "#ff0000"}
    payload = {
        "attachments": [{
            "color": color.get(severity, "#ff9900"),
            "title": f"OTA Alert ({severity.upper()})",
            "text": message,
            "footer": "OTA Monitoring Bot"
        }]
    }
    requests.post(webhook_url, json=payload)
```

### Scheduling / Cron Jobs

```bash
# Run daily at 8am: check all active campaigns
0 8 * * * /usr/bin/python3 /opt/scripts/daily_campaign_report.py >> /var/log/campaign_report.log 2>&1

# Run every 5 minutes: check error rates
*/5 * * * * /usr/bin/python3 /opt/scripts/check_error_rates.py --threshold 0.05
```

```python
# Or use Python's schedule library for long-running scripts
import schedule
import time

def check_campaigns():
    """Check all active campaigns."""
    # ... your logic here ...
    pass

schedule.every(5).minutes.do(check_campaigns)
schedule.every().day.at("08:00").do(generate_daily_report)

while True:
    schedule.run_pending()
    time.sleep(1)
```

## 3.3 Common Ops Scripts You'll Write

| Script | Purpose |
|--------|---------|
| Health checker | Poll services, report status, auto-alert |
| Log aggregator | Collect logs from multiple sources, summarize errors |
| Report generator | Query metrics DB, produce daily/weekly reports |
| Data validator | Check data consistency (fleet registry vs actual) |
| Cleanup tool | Archive old logs, remove stale data, manage storage |
| Migration helper | Bulk update configurations, backfill data |
| Incident helper | Auto-collect relevant logs/metrics when an alert fires |

---

# Module 4: AI Tools for Automation & Productivity

This is a key part of the role — using AI tools to make yourself and your team more productive.

## 4.1 AI Tools Landscape

### Code Assistants

| Tool | What It Does | Best For |
|------|-------------|----------|
| **GitHub Copilot** | Inline code completion in your IDE | Writing code faster, boilerplate |
| **Cursor** | AI-native IDE with chat + code editing | Refactoring, understanding codebases |
| **Claude Code** | CLI agent for complex engineering tasks | Multi-file changes, debugging, research |

### AI Chat / Research

| Tool | Strengths |
|------|-----------|
| **Claude** | Long context, careful reasoning, code generation |
| **ChatGPT** | General knowledge, plugins, browsing |
| Both | Explaining errors, writing scripts, analyzing data, drafting docs |

## 4.2 Practical AI Automation Patterns

### Pattern 1: AI-Powered Log Analysis

```python
"""
Feed error logs to Claude for automated root-cause suggestions.
"""
import anthropic

client = anthropic.Anthropic()

def analyze_errors_with_ai(error_logs: str) -> str:
    """Send error logs to Claude for analysis."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Analyze these error logs from our OTA update platform.
Identify:
1. The most likely root cause
2. Affected scope (how many vehicles, which region)
3. Recommended immediate action
4. Recommended long-term fix

Logs:
{error_logs}"""
        }]
    )
    return message.content[0].text

# Usage
with open("recent_errors.log") as f:
    errors = f.read()
analysis = analyze_errors_with_ai(errors)
print(analysis)
```

### Pattern 2: AI-Generated Reports

```python
def generate_daily_report(metrics: dict) -> str:
    """Use AI to generate a natural language daily report."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Generate a concise daily operations report from these metrics.
Use bullet points. Highlight any anomalies or concerns.
Keep it to 1 page.

Metrics:
- Active campaigns: {metrics['active_campaigns']}
- Updates attempted: {metrics['attempted']}
- Success rate: {metrics['success_rate']:.1%}
- Avg download time: {metrics['avg_download_sec']:.1f}s
- Top error: {metrics['top_error']} ({metrics['top_error_count']} occurrences)
- Vehicles checked in today: {metrics['checkins']}
- Fleet online rate: {metrics['online_rate']:.1%}
"""
        }]
    )
    return message.content[0].text
```

### Pattern 3: AI-Assisted Troubleshooting Runbook

```python
def get_troubleshooting_steps(error_message: str, system_context: str) -> str:
    """Generate troubleshooting steps for a specific error."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system="""You are an operations engineer for an OTA vehicle update platform.
Given an error and system context, provide step-by-step troubleshooting instructions.
Be specific and actionable. Include exact commands to run.""",
        messages=[{
            "role": "user",
            "content": f"Error: {error_message}\n\nSystem context: {system_context}"
        }]
    )
    return message.content[0].text
```

### Pattern 4: Automated Ticket/Issue Creation

```python
def auto_create_ticket(alert_data: dict):
    """When an alert fires, automatically create a Jira ticket with AI-written description."""

    # AI generates a well-structured ticket
    description = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""Write a Jira ticket description for this alert:
Alert: {alert_data['title']}
Severity: {alert_data['severity']}
Service: {alert_data['service']}
Error count: {alert_data['count']}
Time window: {alert_data['window']}
Sample error: {alert_data['sample_error']}

Include: Summary, Impact, Steps to Investigate, Related Dashboards."""
        }]
    ).content[0].text

    # Create the ticket via Jira API
    create_jira_ticket(
        project="OPS",
        title=alert_data["title"],
        description=description,
        priority=alert_data["severity"]
    )
```

## 4.3 Using AI Tools Effectively

### Prompting Tips for Operations Work

```
BAD:  "Fix this error"
GOOD: "Here's an error from our OTA download service. The error started
       at 2:30 AM and affects vehicles in the NA region. Here are the
       last 50 log lines. What's the most likely root cause and what
       should I check first?"

BAD:  "Write a monitoring script"
GOOD: "Write a Python script that:
       1. Queries our Prometheus API for the update_failure_rate metric
       2. Checks if it exceeds 1% in the last 15 minutes
       3. If so, sends a Slack alert with the current rate and top errors
       4. Runs every 5 minutes via cron
       Use the requests library. Our Prometheus is at http://prometheus:9090"
```

### When to Use AI vs When Not To

| Use AI For | Don't Use AI For |
|-----------|-----------------|
| Drafting scripts and tools | Making production changes without review |
| Analyzing logs for patterns | Accessing systems with real credentials |
| Generating reports from data | Security-sensitive decisions |
| Understanding error messages | Replacing human judgment on incidents |
| Writing documentation | Auto-deploying fixes without approval |

---

# Module 5: APIs, Databases & Integration

## 5.1 REST APIs

You'll interact with APIs constantly — internal services, cloud platforms, third-party tools.

### HTTP Methods

```
GET    /vehicles/{vin}           → Read vehicle info
POST   /campaigns                → Create a new campaign
PUT    /campaigns/{id}           → Replace campaign config
PATCH  /campaigns/{id}/status    → Update campaign status
DELETE /campaigns/{id}           → Cancel a campaign
```

### Status Codes You'll See Daily

```
200 OK              — Success
201 Created         — Resource created (POST)
204 No Content      — Success, nothing to return (DELETE)
400 Bad Request     — Your request is malformed
401 Unauthorized    — Missing or invalid auth token
403 Forbidden       — Valid auth but insufficient permissions
404 Not Found       — Resource doesn't exist
409 Conflict        — Conflicting state (e.g., campaign already active)
429 Too Many Reqs   — Rate limited — back off and retry
500 Internal Error  — Server bug
502 Bad Gateway     — Upstream service is down
503 Service Unavail — Server overloaded or in maintenance
504 Gateway Timeout — Upstream service too slow
```

### Working with APIs in Python

```python
import requests

# GET with query params
response = requests.get(
    "https://api.internal/v1/vehicles",
    params={"region": "NA", "status": "pending_update"},
    headers={"Authorization": f"Bearer {token}"},
    timeout=30
)
vehicles = response.json()

# POST with JSON body
response = requests.post(
    "https://api.internal/v1/campaigns",
    json={
        "name": "Security Patch 2026-Q3",
        "target_versions": ["2.0.*"],
        "package_id": "sec-patch-2.1.0",
        "rollout_pct": 1  # Start at 1%
    },
    headers={"Authorization": f"Bearer {token}"}
)
campaign = response.json()

# Handling errors properly
response = requests.get(url, timeout=30)
if response.status_code == 200:
    data = response.json()
elif response.status_code == 404:
    print("Not found")
elif response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    print(f"Rate limited. Retry after {retry_after}s")
else:
    response.raise_for_status()  # Raises exception for 4xx/5xx
```

### curl — Quick API Testing

```bash
# GET
curl -s https://api.internal/v1/health | jq .

# POST with JSON
curl -X POST https://api.internal/v1/campaigns \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "test", "target_versions": ["2.0.*"]}' | jq .

# With verbose output (see headers, TLS info)
curl -v https://api.internal/v1/health

# Download a file
curl -O https://cdn.internal/packages/fw-2.1.0.pkg

# Follow redirects
curl -L https://short.url/abc123
```

## 5.2 Databases

### SQL — The Queries You'll Run Most

```sql
-- How many vehicles updated successfully today?
SELECT COUNT(*) as success_count
FROM update_events
WHERE status = 'SUCCESS'
  AND created_at >= CURRENT_DATE;

-- Failure rate by region for a campaign
SELECT
    region,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
    ROUND(100.0 * SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_pct
FROM update_events
WHERE campaign_id = 'CAMP-123'
GROUP BY region
ORDER BY failure_pct DESC;

-- Top 10 most common error messages
SELECT error_message, COUNT(*) as count
FROM update_events
WHERE status = 'FAILED'
  AND created_at >= NOW() - INTERVAL '24 hours'
GROUP BY error_message
ORDER BY count DESC
LIMIT 10;

-- Vehicles that have been stuck in "downloading" for over 2 hours
SELECT vin, started_at, NOW() - started_at as duration
FROM update_events
WHERE status = 'DOWNLOADING'
  AND started_at < NOW() - INTERVAL '2 hours';

-- Daily update success trend for the past 30 days
SELECT
    DATE(created_at) as day,
    COUNT(*) as total,
    ROUND(100.0 * SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM update_events
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY day;
```

### Python + Database

```python
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    host="db.internal",
    database="ota_platform",
    user="readonly_user",
    password="..."
)

# Quick query with pandas
df = pd.read_sql("""
    SELECT region, status, COUNT(*) as count
    FROM update_events
    WHERE campaign_id = %s
    GROUP BY region, status
""", conn, params=["CAMP-123"])

print(df.pivot(index="region", columns="status", values="count").fillna(0))
```

---

# Module 6: Linux & Cloud Fundamentals

## 6.1 Essential Linux Commands

```bash
# --- System Info ---
uname -a                    # OS and kernel version
df -h                       # Disk usage
free -h                     # Memory usage
top / htop                  # Process monitoring
uptime                      # How long system has been running

# --- Process Management ---
ps aux | grep ota-agent     # Find a process
kill -15 <pid>              # Graceful stop (SIGTERM)
systemctl status ota-agent  # Check service status
journalctl -u ota-agent -f  # Follow service logs

# --- File Operations ---
find /var/log -name "*.log" -mtime +30 -delete  # Delete logs older than 30 days
du -sh /var/log/*           # Disk usage by directory
tar -czf logs-backup.tar.gz /var/log/ota/       # Compress logs

# --- Networking ---
curl -I https://cdn.internal/health     # Check HTTP headers
ping -c 3 ota-api.internal              # Basic connectivity
nslookup ota-api.internal               # DNS resolution
netstat -tlnp                           # Listening ports
ss -tlnp                                # Modern alternative to netstat

# --- SSH to Remote Servers ---
ssh user@server.internal
ssh -L 8080:localhost:8080 user@server   # Port forwarding
scp file.py user@server:/tmp/            # Copy file to remote
```

## 6.2 Cloud Platforms (AWS Focus)

Key AWS services you'll encounter:

| Service | Purpose in OTA Context |
|---------|----------------------|
| **S3** | Store update packages, logs, reports |
| **EC2** | Run backend services |
| **RDS** | PostgreSQL database for vehicle registry, campaigns |
| **CloudFront** | CDN for distributing update packages |
| **CloudWatch** | Logs, metrics, alarms |
| **Lambda** | Event-driven automation (process upload, trigger alerts) |
| **SQS/SNS** | Message queues, notifications |
| **IAM** | Access control and permissions |

### AWS CLI Basics

```bash
# S3
aws s3 ls s3://ota-packages/                          # List bucket
aws s3 cp firmware.pkg s3://ota-packages/v2.1/        # Upload
aws s3 sync ./reports s3://ota-reports/2026-09/        # Sync directory

# CloudWatch Logs
aws logs filter-log-events \
  --log-group-name /ota/api \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s000)

# EC2
aws ec2 describe-instances --filters "Name=tag:Service,Values=ota-api"
```

---

# Module 7: Monitoring, Reporting & Dashboards

## 7.1 Monitoring Stack

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Application  │────>│  Prometheus  │────>│  Grafana    │
│ (metrics     │     │  (collect &  │     │  (visualize │
│  endpoint)   │     │   store)     │     │   & alert)  │
└─────────────┘     └──────────────┘     └─────────────┘

┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Application  │────>│  ELK Stack   │────>│  Kibana     │
│ (JSON logs)  │     │  or Datadog  │     │  (search &  │
│              │     │  (aggregate) │     │   visualize) │
└─────────────┘     └──────────────┘     └─────────────┘
```

### Common Monitoring Tools

| Tool | Type | Purpose |
|------|------|---------|
| **Grafana** | Dashboards | Visualize metrics, create alerts |
| **Prometheus** | Metrics | Collect and store time-series metrics |
| **Datadog** | Full platform | Metrics + logs + traces + alerts |
| **ELK Stack** | Logs | Elasticsearch + Logstash + Kibana for log search |
| **PagerDuty / OpsGenie** | Alerting | Route alerts to on-call engineers |
| **Splunk** | Logs + analytics | Enterprise log analysis |

## 7.2 Building Reports with Python

```python
"""
Automated daily operations report.
Queries metrics, generates summary, sends to Slack.
"""
import pandas as pd
from datetime import datetime, timedelta

def generate_daily_report(db_conn, slack_webhook):
    yesterday = datetime.now() - timedelta(days=1)

    # Query key metrics
    df = pd.read_sql("""
        SELECT
            status,
            COUNT(*) as count,
            AVG(duration_sec) as avg_duration,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_sec) as p99_duration
        FROM update_events
        WHERE created_at >= %s
        GROUP BY status
    """, db_conn, params=[yesterday])

    total = df["count"].sum()
    success = df[df["status"] == "SUCCESS"]["count"].sum()
    failed = df[df["status"] == "FAILED"]["count"].sum()
    success_rate = success / total if total > 0 else 0

    report = f"""
*Daily OTA Report — {yesterday.strftime('%Y-%m-%d')}*

*Updates*: {total:,} attempted
*Success Rate*: {success_rate:.1%} ({success:,} succeeded, {failed:,} failed)
*Avg Duration*: {df['avg_duration'].mean():.0f}s
*P99 Duration*: {df['p99_duration'].max():.0f}s

{"⚠️ *Alert*: Success rate below 99%!" if success_rate < 0.99 else "✅ All metrics healthy."}
    """

    # Send to Slack
    requests.post(slack_webhook, json={"text": report})
    return report
```

---

# Module 8: Connected Devices & OTA Operations Context

## 8.1 How OTA Fits Into Vehicle Operations

Your daily work will revolve around making sure updates get to vehicles reliably:

```
┌─────────────────────────────────────────────────┐
│            YOUR ROLE IN THE OTA LIFECYCLE         │
│                                                   │
│  Build Team creates update package                │
│       │                                           │
│       ▼                                           │
│  QA validates in test environment                 │
│       │                                           │
│       ▼                                           │
│  ★ YOU: Monitor campaign rollout ★                │
│  ★ YOU: Investigate failures ★                    │
│  ★ YOU: Analyze metrics and logs ★                │
│  ★ YOU: Build tools to automate above ★           │
│  ★ YOU: Report on fleet health ★                  │
│       │                                           │
│       ▼                                           │
│  Campaign completes → post-mortem if issues       │
└─────────────────────────────────────────────────┘
```

## 8.2 Key Concepts for Connected Vehicle Platforms

### Vehicle Lifecycle

```
Manufacturing → Provisioning → Active → Updating → Decommission
                    │                      │
              Assign VIN,            OTA campaigns,
              initial SW,            monitoring,
              register in            troubleshooting
              fleet DB
```

### Fleet Management

```python
# Typical fleet queries you'll run:
# "How many vehicles are on version 2.0.x?"
# "Which vehicles haven't checked in this week?"
# "What's the update status for the Q3 security campaign?"
# "Show me all vehicles in Korea running firmware < 1.9"
```

### Campaign Operations Checklist

```
Before Launch:
  □ Package tested in staging environment
  □ Compatible hardware revisions confirmed
  □ Rollback plan documented
  □ Monitoring dashboards ready
  □ Alert thresholds configured
  □ On-call engineer assigned

During Rollout:
  □ Monitor success/failure rates
  □ Watch for anomalies in download times
  □ Check vehicle health post-update
  □ Respond to alerts
  □ Adjust rollout speed if issues found

After Completion:
  □ Generate campaign summary report
  □ Document any issues encountered
  □ Update runbooks with new learnings
  □ Close related tickets
```

---

# Resources & Study Schedule

## Priority Study Order

Given the actual job description, focus on these in order:

| Priority | Topic | Module | Why |
|----------|-------|--------|-----|
| 1 | Python scripting + automation | Module 3 | Daily tool building |
| 2 | Log analysis + monitoring | Module 2 | Daily investigation work |
| 3 | AI tools for automation | Module 4 | Explicitly in the JD |
| 4 | APIs + databases (SQL) | Module 5 | Querying systems, integrations |
| 5 | Root-cause analysis | Module 1 | Core skill for troubleshooting |
| 6 | Linux + cloud basics | Module 6 | Working with infrastructure |
| 7 | Monitoring + dashboards | Module 7 | Reporting and visibility |
| 8 | OTA/connected device context | Module 8 | Domain knowledge |

## Suggested Study Schedule (4 weeks)

| Week | Focus | Actions |
|------|-------|---------|
| 1 | Python + APIs | Write 3 automation scripts. Practice requests library. Write SQL queries. |
| 2 | Logs + Linux | Practice jq, grep, log analysis. Set up a Linux VM. AWS CLI basics. |
| 3 | AI tools | Build an AI-powered log analyzer. Use Claude API. Try Cursor for code tasks. |
| 4 | Domain + integration | Read about OTA systems (Module 8 + the OTA study guide). Practice RCA on sample incidents. |

## Online Resources

### Python for Operations
- **Automate the Boring Stuff with Python**: https://automatetheboringstuff.com/ — Free online book, excellent for scripting fundamentals
- Search YouTube: **"python automation scripts tutorial"** — Practical walkthroughs
- Search YouTube: **"python requests library API tutorial"** — Working with REST APIs

### Log Analysis
- **jq Manual**: https://jqlang.github.io/jq/manual/ — Reference for the jq JSON processor
- Search YouTube: **"linux log analysis tutorial"** — grep, awk, jq patterns
- Search YouTube: **"ELK stack tutorial"** — Understanding centralized logging

### SQL
- **SQLBolt**: https://sqlbolt.com/ — Interactive SQL tutorial, free
- **Mode SQL Tutorial**: https://mode.com/sql-tutorial — Analytics-focused SQL
- Search YouTube: **"SQL for data analysis tutorial"**

### AI Tools
- **Anthropic Claude API docs**: https://docs.anthropic.com/ — Building with Claude
- **GitHub Copilot docs**: https://docs.github.com/en/copilot
- Search YouTube: **"claude api python tutorial"**, **"cursor ai ide tutorial"**

### Linux & Cloud
- **Linux Journey**: https://linuxjourney.com/ — Free, beginner-friendly
- **AWS Cloud Practitioner**: Search for free training on AWS Skill Builder
- Search YouTube: **"linux command line for beginners"**, **"aws basics tutorial"**

### Monitoring & Observability
- **Grafana tutorials**: https://grafana.com/tutorials/
- **Prometheus docs**: https://prometheus.io/docs/introduction/overview/
- Search YouTube: **"grafana prometheus monitoring tutorial"**

### OTA / Connected Vehicles
- Refer to the existing OTA study guide at: `../../study/ota-systems/ota-study-guide.md`
- Search YouTube: **"automotive OTA update explained"**, **"connected car platform architecture"**
