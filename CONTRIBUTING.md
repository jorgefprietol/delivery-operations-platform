# Contributing

Use a focused pull request with a concrete operational problem, evidence and recovery notes where relevant. Run the checks documented in README before submitting. Changes to release states require tests covering invalid transitions and concurrency. Regenerate Python locks with `uv pip compile --python-version 3.12 --universal --generate-hashes`; never edit dependency hashes manually.

Regenerate dashboard JSON with `python scripts/build-dashboard.py` and review the diff. Changes to immutable image references should preserve verification and supply-chain evidence. Do not commit credentials, delivery records, Terraform state, plans or generated reports.
