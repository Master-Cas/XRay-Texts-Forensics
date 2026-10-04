import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app

runner = CliRunner()


def test_blackbox_selftest_cli_json() -> None:
    result = runner.invoke(
        app,
        [
            "blackbox-selftest",
            "--permutations",
            "199",
            "--samples-per-cell",
            "35",
            "--alpha",
            "0.01",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["validated"] is True
    assert payload["off"]["significant"] is False
    assert payload["on"]["significant"] is True
