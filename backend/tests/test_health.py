from app import main
from sqlalchemy.exc import SQLAlchemyError


def test_health_checks_database_readiness(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["version"]
    assert response.headers["x-request-id"]


def test_liveness_does_not_depend_on_database(client, monkeypatch):
    def fail_if_called():
        raise AssertionError("Liveness must not check downstream dependencies")

    monkeypatch.setattr(main, "_database_ready", fail_if_called)
    response = client.get("/api/live", headers={"X-Request-ID": "synthetic-check-1"})

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert response.headers["x-request-id"] == "synthetic-check-1"


def test_admin_metrics_are_protected_and_report_bounded_metrics(client):
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert "drillloop_http_requests_total" in response.text
    assert "drillloop_db_pool_checked_out" in response.text
    assert "drillloop_db_pool_peak_checked_out" in response.text

    client.post("/api/auth/logout")
    login = client.post(
        "/api/auth/login",
        json={"username": "test-viewer", "password": "test-only-password-for-suite"},
    )
    client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
    response = client.get("/api/metrics")
    assert response.status_code == 403


def test_health_hides_database_error_and_returns_not_ready(client, monkeypatch):
    class UnavailableSession:
        def __enter__(self):
            raise SQLAlchemyError("connection details must not reach the caller")

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(main, "SessionLocal", UnavailableSession)
    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "DATABASE_NOT_READY",
        "message": "The application database is not ready.",
    }
    assert "connection details" not in response.text
