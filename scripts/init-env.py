import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser(description="Generate local credentials without overwriting them")
parser.add_argument("--output", default=".env")
args = parser.parse_args()
target = Path(args.output)
with target.open("x", encoding="utf-8") as handle:
    for name in ("OPERATOR_TOKEN", "APPROVER_TOKEN", "GRAFANA_PASSWORD"):
        handle.write(f"{name}={secrets.token_urlsafe(36)}\n")
print(f"Credentials created in {target}. Keep this file private.")
