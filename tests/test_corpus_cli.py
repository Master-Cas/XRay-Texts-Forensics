import json

from typer.testing import CliRunner

from xray_text_forensics.cli import app

runner = CliRunner()


def test_compare_corpora_cli_json(tmp_path) -> None:
    corpus_a = tmp_path / "a"
    corpus_b = tmp_path / "b"
    corpus_a.mkdir()
    corpus_b.mkdir()
    (corpus_a / "one.txt").write_text("apple orchard apple tree", encoding="utf-8")
    (corpus_b / "one.txt").write_text("engine motor engine wheel", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "compare-corpora",
            str(corpus_a),
            str(corpus_b),
            "--store",
            str(tmp_path / "store"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["corpus_a"]["document_count"] == 1
    assert payload["corpus_b"]["document_count"] == 1
    terms = {row["term"]: row for row in payload["specificity"]}
    assert terms["apple"]["direction"] == "A"
    assert terms["engine"]["direction"] == "B"
