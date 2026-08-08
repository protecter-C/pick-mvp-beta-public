from fastapi.testclient import TestClient
from app.main import app

def test_health_readiness_and_admin_export_are_safe():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"
        assert client.get("/admin/metrics/export").status_code == 403
        exported = client.get("/admin/metrics/export", headers={"X-Admin-Key": "test-admin"})
        assert exported.status_code == 200
        assert exported.json()["format"] == "json"
        assert exported.json()["retention_days"] >= 7
