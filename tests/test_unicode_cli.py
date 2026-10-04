import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app

runner = CliRunner()


def test_unicode_cli_json(tmp_path) -> None:
    evidence = tmp_path / "unicode.txt"
    evidence.write_text("ab\u200bcd", encoding="utf-8")

    result = runner.invoke(
        app,
        ["unicode", str(evidence), "--store", str(tmp_path / "store"), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    matches = [
        item
        for item in payload["evidence"]
        if item["finding"] == "ZERO_WIDTH_CHARACTER"
    ]
    assert matches[0]["status"] == "DETECTED"
    assert matches[0]["locations"][0]["start"] == 2
