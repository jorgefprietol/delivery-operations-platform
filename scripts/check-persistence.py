import json
import os
import time
from pathlib import Path

import httpx

for line in Path(".env").read_text().splitlines():
    if "=" in line:
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)
baseline = json.loads(Path("artifacts/e2e.json").read_text())["summary"]
base_url = os.getenv("API_URL", "http://127.0.0.1:18095")
for _attempt in range(30):
    try:
        ready = httpx.get(base_url + "/health/ready", timeout=3)
        if ready.status_code == 200:
            break
    except httpx.TransportError:
        pass
    time.sleep(1)
else:
    raise RuntimeError("API did not recover after restart")
response = httpx.get(
    base_url + "/api/v1/summary",
    headers={"Authorization": "Bearer " + os.environ["OPERATOR_TOKEN"]},
    timeout=10,
)
response.raise_for_status()
after = response.json()
for key in ("production_deployments", "recovered_incidents", "open_incidents", "active"):
    assert baseline[key] == after[key], f"Persistence mismatch: {key}"
print("PASS: release history and active environments survive container restart")
