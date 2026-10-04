import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app

runner = CliRunner()


def test_calibration_cli_json(tmp_path) -> None:
    controls = tmp_path / "controls.jsonl"
    test = tmp_path / "test.jsonl"

    controls.write_text(
        "".join(
            json.dumps(
                {
                    "sample_id": f"n{i}",
                    "label": False,
                    "score": i / 200,
                    "length": 100,
                }
            )
            + "\n"
            for i in range(200)
        ),
        encoding="utf-8",
    )
    test.write_text(
        "".join(
            [
                json.dumps(
                    {
                        "sample_id": "neg",
                        "label": False,
                        "score": 0.1,
                        "length": 100,
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "sample_id": "pos",
                        "label": True,
                        "score": 2.0,
                        "length": 100,
                    }
                )
                + "\n",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "calibrate-scores",
            str(controls),
            str(test),
            "--detector-id",
            "demo",
            "--dataset-id",
            "demo-set",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["manifest"]["dev_empirical_fpr"] <= 0.01
    assert payload["fpr"] == 0.0
    assert payload["tpr"] == 1.0
