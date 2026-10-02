# Security policy

Report vulnerabilities privately through GitHub's private vulnerability reporting when available. Do not publish active credentials or exploitable details in public issues.

This project uses role-level local credentials. Protect the Docker host, SQLite volume, Terraform state and .env file. For remote exposure, add TLS, authenticated access to metrics and an identity provider. Dependency and image updates require the same quality and integration gates as application changes.
