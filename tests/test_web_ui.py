from pathlib import Path

from fastapi.testclient import TestClient

from xray_text_forensics.web import WebSettings, create_app


def client(tmp_path) -> TestClient:
    return TestClient(create_app(WebSettings(data_root=tmp_path / "data")))


def test_product_ui_is_served_with_strict_browser_headers(tmp_path) -> None:
    response = client(tmp_path).get("/")
    assert response.status_code == 200
    assert "XRay Texts Forensics" in response.text
    assert 'src="/static/app.js"' in response.text
    assert 'href="/static/app.css"' in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "'unsafe-inline'" not in csp


def test_static_assets_are_same_origin_and_javascript_avoids_inner_html(tmp_path) -> None:
    web = client(tmp_path)
    script = web.get("/static/app.js")
    stylesheet = web.get("/static/app.css")

    assert script.status_code == 200
    assert stylesheet.status_code == 200
    assert "innerHTML" not in script.text
    assert "textContent" in script.text
    assert "https://" not in script.text
    assert "https://" not in stylesheet.text


def test_ui_package_data_is_declared() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    declaration = (
        '"xray_text_forensics.web" = '
        '["static/*.html", "static/*.css", "static/*.js"]'
    )
    assert declaration in pyproject


def test_api_still_has_security_headers(tmp_path) -> None:
    response = client(tmp_path).get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
