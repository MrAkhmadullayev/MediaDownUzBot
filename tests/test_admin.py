from fastapi.testclient import TestClient

from app.admin.main import create_app
from app.config import Settings


def test_live_health_and_security_headers() -> None:
    app = create_app(Settings())
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "script-src 'self'" in response.headers["content-security-policy"]


def test_admin_requires_session() -> None:
    app = create_app(Settings())
    with TestClient(app) as client:
        response = client.get("/admin")
    assert response.status_code == 401
    assert "Admin panel" in response.text
    assert 'href="/static/admin.css"' in response.text
    assert 'src="/static/admin.js"' in response.text
    assert "http://localhost" not in response.text


def test_admin_templates_compile() -> None:
    app = create_app(Settings())
    with TestClient(app):
        app.state.templates.get_template("admin.html")
        app.state.templates.get_template("access_denied.html")
