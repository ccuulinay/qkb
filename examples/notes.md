# notes.md — sample knowledge file

## Authentication
Internal services use mTLS for service-to-service auth. Tokens expire after 60 minutes.
Refresh is automatic via the sidecar.

## Database
We use Postgres 16 in production. Schema migrations live in `infra/migrations/`.
For local development, a SQLite shim is fine.

## Logging
Structured JSON logs with a `request_id` field for tracing.
Levels: DEBUG, INFO, WARN, ERROR.
