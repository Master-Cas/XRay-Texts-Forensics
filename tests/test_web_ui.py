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


def test_quick_scan_includes_plain_language_evidence_layer(tmp_path) -> None:
    web = client(tmp_path)
    page = web.get("/")
    script = web.get("/static/app.js")

    assert "AI / human statistical classification" in page.text
    assert "Run full forensic scan" in page.text
    assert "Show technical Unicode evidence" in page.text
    assert "Clasificación estadística, no prueba criptográfica de procedencia." in page.text
    assert "never as negative evidence" in page.text

    assert '"/analyze/full"' in script.text
    assert "Reference comparison available" in script.text
    assert "AI likely" in script.text
    assert "Human likely" in script.text
    assert "Inconclusive" in script.text
    assert "Classifier unavailable" in script.text
    assert "Origin not testable yet" in script.text
    assert "Hidden zero-width characters" in script.text
    assert "Words mixing look-alike alphabets" in script.text
    assert "Unicode representation changes after normalization" in script.text
    assert "Build your reference corpora" in page.text
    assert "Known-origin library" in page.text
    assert "Global XRay baseline" in page.text
    assert "New private reference set" in page.text
    assert '"/references/status"' in script.text
    assert "Add known-origin samples" in script.text
    assert ".odt" in script.text
    assert "incomplete private sets never disable the global baseline" in script.text


def test_authorship_and_reference_origin_use_distinct_ui_surfaces(tmp_path) -> None:
    web = client(tmp_path)
    page = web.get("/")
    script = web.get("/static/app.js")
    assert page.status_code == 200
    assert script.status_code == 200

    assert "AI / human statistical classification" in page.text
    assert "Reference comparison status" in page.text
    assert "not proof of an author's identity" in page.text
    assert 'aria-labelledby="reference-origin-title"' in page.text
    for target in (
        "origin-badge", "origin-title", "origin-text",
        "reference-origin-badge", "reference-origin-title", "reference-origin-text",
    ):
        assert page.text.count(f'id="{target}"') == 1

    authorship = script.text.split("function renderAuthorshipAssessment(", 1)[1].split(
        "function renderOriginAssessment(", 1
    )[0]
    reference_origin = script.text.split("function renderOriginAssessment(", 1)[1].split(
        "function renderReferenceComparison(", 1
    )[0]
    for target in ("origin-badge", "origin-title", "origin-text"):
        assert f'$("{target}")' in authorship
        assert f'$("{target}")' not in reference_origin
    for target in ("reference-origin-badge", "reference-origin-title", "reference-origin-text"):
        assert f'$("{target}")' in reference_origin
        assert f'$("{target}")' not in authorship

    scan = script.text.split("async function scanFile(", 1)[1].split(
        "function reportUrl(", 1
    )[0]
    authorship_call = "renderAuthorshipAssessment(result.authorship_assessment);"
    reference_call = "renderOriginAssessment(result.origin_assessment);"
    assert authorship_call in scan
    assert reference_call in scan
    assert scan.index(authorship_call) < scan.index(reference_call)
    assert "renderReferenceComparison(result.reference_comparison);" in scan
