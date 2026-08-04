import re

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
    assert re.search(r'href="/static/admin\.css\?v=[0-9a-f]{12}"', response.text)
    assert re.search(r'src="/static/admin\.js\?v=[0-9a-f]{12}"', response.text)
    assert "http://localhost" not in response.text


def test_static_assets_are_content_versioned_and_cacheable() -> None:
    app = create_app(Settings(APP_ENV="production"))
    with TestClient(app) as client:
        admin_response = client.get("/admin")
        asset_urls = re.findall(
            r'["\'](/static/(?:admin\.css|admin\.js)\?v=[0-9a-f]{12})["\']',
            admin_response.text,
        )
        assert len(asset_urls) == 2

        for asset_url in asset_urls:
            asset_response = client.get(asset_url)
            assert asset_response.status_code == 200
            assert asset_response.headers["cache-control"] == (
                "public, max-age=31536000, immutable"
            )

        unversioned_response = client.get("/static/admin.css")
        assert unversioned_response.headers["cache-control"] == "no-cache"


def test_admin_templates_compile() -> None:
    app = create_app(Settings())
    with TestClient(app):
        app.state.templates.get_template("admin.html")
        app.state.templates.get_template("access_denied.html")
