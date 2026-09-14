"""Verifies the FastAPI app boots and can talk to the database."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_reports_database_connected():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
