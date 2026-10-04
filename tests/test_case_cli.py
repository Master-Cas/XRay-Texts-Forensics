import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app

runner = CliRunner()


def test_case_cli_end_to_end(tmp_path) -> None:
    database = tmp_path / "cases.sqlite"
    objects = tmp_path / "objects"
    evidence_file = tmp_path / "evidence.txt"
    evidence_file.write_text("ab\u200bcd", encoding="utf-8")

    created = runner.invoke(
        app,
        ["case-create", str(database), "CLI Case", "--json"],
    )
    assert created.exit_code == 0, created.output
    case_id = json.loads(created.output)["case_id"]

    imported = runner.invoke(
        app,
        [
            "case-import-unicode",
            str(database),
            case_id,
            str(evidence_file),
            "--store",
            str(objects),
            "--json",
        ],
    )
    assert imported.exit_code == 0, imported.output
    bundle = json.loads(imported.output)
    assert bundle["audit_verified"] is True
    assert bundle["evidence"]

    verified = runner.invoke(app, ["case-verify", str(database), case_id])
    assert verified.exit_code == 0
    assert "VERIFIED" in verified.output

    html_report = tmp_path / "report.html"
    rendered = runner.invoke(
        app,
        [
            "case-report",
            str(database),
            case_id,
            str(html_report),
            "--format",
            "html",
        ],
    )
    assert rendered.exit_code == 0, rendered.output
    assert html_report.exists()
    assert "XRay Forensic Report" in html_report.read_text(encoding="utf-8")
