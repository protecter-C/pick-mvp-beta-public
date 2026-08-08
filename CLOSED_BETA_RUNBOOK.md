# PICK closed-beta operations

## Environment checklist

- Set `ENVIRONMENT=production` and a reachable PostgreSQL `DATABASE_URL`.
- Set unique, secret `AUTH_SECRET`, `AFFILIATE_WEBHOOK_SECRET`, and `ADMIN_API_KEY` values.
- Set `ANALYTICS_RETENTION_DAYS` (7–3650 days) and optional `ANALYTICS_EXPORT_PATH`.
- Run `alembic upgrade head` before starting the API.
- Confirm `GET /health` and `GET /ready` both succeed.
- Restrict `/admin/metrics` and `/admin/metrics/export` to the operations network and `X-Admin-Key` secret.

## Operations

- Use `/admin/metrics?days=30` for aggregate counts only; no raw event endpoint is exposed.
- Export the same aggregate view from `/admin/metrics/export` when `ANALYTICS_EXPORT_PATH` is configured.
- Rotate admin and webhook secrets using the deployment secret manager.
- Alert on readiness failures, 5xx logs (`api_request_error`), and scheduler refresh errors.
- Verify a restart preserves users, watches, price history, conversions, points, and analytics events.
