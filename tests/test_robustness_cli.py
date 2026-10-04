import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app
from xray_text_forensics.detectors.watermark import generate_reference_watermarked_text

runner = CliRunner()


def test_watermark_stress_cli_json(tmp_path, monkeypatch) -> None:
    secret = "ROBUSTNESS_CLI_SECRET"
    monkeypatch.setenv("XRAY_ROBUSTNESS_KEY", secret)
    path = tmp_path / "watermarked.txt"
    path.write_text(
        generate_reference_watermarked_text(secret=secret.encode(), token_count=220),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "watermark-stress",
            str(path),
            "--key-env",
            "XRAY_ROBUSTNESS_KEY",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["baseline"]["status"] == "DETECTED"
    assert secret not in result.output


def test_compare_transform_cli_json(tmp_path) -> None:
    original = tmp_path / "original.txt"
    transformed = tmp_path / "transformed.txt"
    original.write_text("alpha beta gamma delta epsilon", encoding="utf-8")
    transformed.write_text("alpha beta gamma delta epsilon", encoding="utf-8")

    result = runner.invoke(
        app,
        ["compare-transform", str(original), str(transformed), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["fivegram_survival"] == 1.0
    assert payload["lexical_tfidf_cosine"] == 1.0
