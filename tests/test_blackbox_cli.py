import json

from typer.testing import CliRunner

from xray_text_forensics.blackbox import (
    SyntheticChoiceEndpoint,
    collect_observations,
    default_validation_design,
)
from xray_text_forensics.blackbox.io import save_observations_jsonl
from xray_text_forensics.cli import app

runner = CliRunner()


def test_blackbox_validate_cli_json() -> None:
    result = runner.invoke(
        app,
        ["blackbox-validate", "--permutations", "199", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["passed"] is True
    assert payload["off_result"]["p_value"] > payload["alpha"]
    assert payload["on_result"]["p_value"] <= payload["alpha"]


def test_blackbox_analyze_cli_json(tmp_path) -> None:
    design = default_validation_design(seed=99, repeats=8)
    rows = collect_observations(
        design,
        SyntheticChoiceEndpoint(secret=b"key", seed=99),
    )
    path = tmp_path / "rows.jsonl"
    save_observations_jsonl(path, rows)

    result = runner.invoke(
        app,
        [
            "blackbox-analyze",
            str(path),
            "--permutations",
            "99",
            "--seed",
            "1",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["valid_observations"] == len(rows)
    assert payload["choice_count"] == len(design.choices)
