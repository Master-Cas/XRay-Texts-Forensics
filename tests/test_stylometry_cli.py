import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app

runner = CliRunner()


def test_stylometry_cli_json(tmp_path) -> None:
    refs = tmp_path / "refs"
    short = refs / "short"
    long = refs / "long"
    short.mkdir(parents=True)
    long.mkdir()
    (short / "a.txt").write_text("One. Two. Three. Four.", encoding="utf-8")
    (short / "b.txt").write_text("Red. Blue. Green. Gold.", encoding="utf-8")
    (long / "a.txt").write_text(
        "This reference corpus uses longer sentences with several clauses and more words.",
        encoding="utf-8",
    )
    (long / ".xray-reference.json").write_text(
        json.dumps({"label": "long", "source": "synthetic", "topic": "demo"}),
        encoding="utf-8",
    )
    suspect = tmp_path / "suspect.txt"
    suspect.write_text("Sun. Moon. Star. Sky.", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "stylometry-compare",
            str(suspect),
            str(refs),
            "--store",
            str(tmp_path / "store"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["comparisons"]) == 2
    assert "authorship" in payload["scientific_note"].lower()
