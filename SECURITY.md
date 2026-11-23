# Security notes

| Risk | Control |
|---|---|
| Secrets in git | `.env` is git-ignored; only `.env.example` placeholders are committed; gitleaks pre-commit hook; no JSON keys anywhere — GCP access via Application Default Credentials (browser login), never a key file |
| API abuse | API key compared with `hmac.compare_digest`; refuses to start with a key shorter than 16 chars; per-key rate limit; 1 MB body limit; 1000-event batch limit; OpenAPI/docs endpoints disabled |
| Malicious payloads | Pydantic `extra="forbid"`, strict ID patterns (blocks injection-style IDs), numeric ranges, enum checks; invalid input is quarantined, never executed |
| SQL injection | No user text is interpolated into SQL (BigQuery/DuckDB use parameters); the KPI assistant only runs static allowlisted templates on a read-only connection |
| Alert webhook | `https` scheme enforced, 10 s timeout, URL from env only |
| Containers | Non-root user, slim image, read-only root fs for the API, `no-new-privileges`, all ports bound to `127.0.0.1`, no default passwords (compose fails without `.env` values) |
| Supply chain | Dependabot (pip, Actions, Docker), `pip-audit` in CI (informational), bandit in CI |
| PII | None — all identifiers are synthetic |

Known limits: the rate limiter is in-memory (per instance); the API is meant for local/trusted-network use (if exposed publicly, put a gateway/WAF in front); Airflow `standalone` in compose is for local demos only.
