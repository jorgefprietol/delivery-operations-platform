"""Generate the checked-in Grafana dashboard deterministically."""

import json
from pathlib import Path

specifications = [
    ("Production deployments · 30d", "delivery_production_deployments_30d", "short"),
    ("Change failure rate · 30d", "delivery_change_failure_ratio_30d", "percentunit"),
    ("Mean lead time · 30d", "delivery_mean_lead_time_seconds_30d", "s"),
    ("Mean recovery time · 30d", "delivery_mean_recovery_time_seconds_30d", "s"),
    ("HTTP requests / second", "sum(rate(delivery_http_requests_total[5m]))", "reqps"),
    (
        "HTTP p95 latency",
        "histogram_quantile(0.95, sum by (le) (rate(delivery_http_duration_seconds_bucket[5m])))",
        "s",
    ),
]
panels = []
for index, (title, expression, unit) in enumerate(specifications):
    panels.append(
        {
            "id": index + 1,
            "title": title,
            "type": "stat" if index < 4 else "timeseries",
            "datasource": {"type": "prometheus", "uid": "delivery-prometheus"},
            "gridPos": {
                "h": 7 if index < 4 else 9,
                "w": 6 if index < 4 else 12,
                "x": index * 6 if index < 4 else (index - 4) * 12,
                "y": 0 if index < 4 else 7,
            },
            "targets": [{"refId": "A", "expr": expression}],
            "fieldConfig": {"defaults": {"unit": unit, "noValue": "No data"}, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
        }
    )
dashboard = {
    "uid": "delivery-operations",
    "title": "Delivery Operations | Engineering Overview",
    "description": "Production delivery records over a rolling 30-day window; live HTTP telemetry.",
    "schemaVersion": 41,
    "version": 1,
    "tags": ["delivery", "platform-engineering"],
    "refresh": "10s",
    "time": {"from": "now-1h", "to": "now"},
    "panels": panels,
}
target = Path("observability/grafana/dashboards/delivery.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(dashboard, indent=2) + "\n", encoding="utf-8")
