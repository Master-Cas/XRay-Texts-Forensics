import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app
from xray_text_forensics.detectors.watermark import generate_reference_watermarked_text

runner = CliRunner()


def test_watermark_cli_uses_env_secret_without_echoing_value(tmp_path, monkeypatch) -> None:
    key = "CLI_SUPER_SECRET_VALUE"
    monkeypatch.setenv("XRAY_TEST_WATERMARK_KEY", key)
    evidence = tmp_path / "watermarked.txt"
    evidence.write_text(
        generate_reference_watermarked_text(secret=key.encode(), token_count=220),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "watermark-redgreen",
            str(evidence),
            "--key-env",
            "XRAY_TEST_WATERMARK_KEY",
            "--store",
            str(tmp_path / "store"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    item = payload["evidence"][0]
    assert item["status"] == "DETECTED"
    assert item["parameters"]["secret_ref"] == "XRAY_TEST_WATERMARK_KEY"
    assert key not in result.output
