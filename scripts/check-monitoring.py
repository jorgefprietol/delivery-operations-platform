import json
import os
import time
from pathlib import Path

import httpx

if Path(".env").exists():
    for line in Path(".env").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)

grafana = os.getenv("GRAFANA_URL", "http://127.0.0.1:13095")
prometheus = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:19095")
with httpx.Client(auth=("admin", os.environ["GRAFANA_PASSWORD"]), timeout=15) as client:
    dashboard = client.get(grafana + "/api/dashboards/uid/delivery-operations")
    dashboard.raise_for_status()
    panels = dashboard.json()["dashboard"]["panels"]
    assert len(panels) == 6
    sources = client.get(grafana + "/api/datasources/uid/delivery-prometheus")
    sources.raise_for_status()
    assert sources.json()["url"] == "http://prometheus:9090"

for _attempt in range(20):
    response = httpx.get(
        prometheus + "/api/v1/query",
        params={"query": "delivery_production_deployments_30d"},
        timeout=10,
    )
    response.raise_for_status()
    result = response.json()["data"]["result"]
    if result and float(result[0]["value"][1]) >= 2:
        break
    time.sleep(2)
else:
    raise RuntimeError("No delivery business metrics in Prometheus")
rules = httpx.get(prometheus + "/api/v1/rules", timeout=15).json()
assert len(rules["data"]["groups"][0]["rules"]) == 3
Path("artifacts/monitoring.json").write_text(
    json.dumps({"result": "passed", "panels": len(panels), "rules": 3, "scraped": True}, indent=2)
)
print("PASS: Grafana dashboard, datasource, Prometheus business metrics and alert rules")
