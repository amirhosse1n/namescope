from fastapi.testclient import TestClient

from namescope.app import create_app


def test_health_and_security_headers(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["name"] == "NameScope"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["cache-control"] == "no-store"


def test_index_contains_no_internal_version_or_local_app_badge(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Local app" not in response.text
        assert "Local-first username research" not in response.text


def test_invalid_scan_is_rejected_before_job_creation(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/scans",
            json={
                "platform": "telegram",
                "min_length": 3,
                "max_length": 3,
                "count": 10,
                "include_letters": True,
                "include_digits": False,
                "include_underscore": False,
                "include_hyphen": False,
                "include_period": False,
                "custom_characters": "",
                "strategy": "random",
            },
        )
        assert response.status_code == 422


def test_history_endpoints_use_temp_database(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/history/github?limit=1")
        assert response.status_code == 200
        assert response.json()["count"] == 0
        cleared = client.delete("/api/history/github")
        assert cleared.status_code == 200
