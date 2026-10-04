import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app

runner = CliRunner()


def test_cli_ingest_json(tmp_path) -> None:
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("hello forensic world", encoding="utf-8")

    result = runner.invoke(
        app,
        ["ingest", str(evidence), "--store", str(tmp_path / "store"), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifact"]["media_type"] == "text/plain"
    assert payload["artifact"]["sha256"]
    assert len(payload["views"]) == 2
