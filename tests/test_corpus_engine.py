from xray_text_forensics.corpus import CorpusDocument, CorpusEngine
from xray_text_forensics.corpus.tokenize import paragraph_contexts, sentence_contexts, tokenize


def docs(*texts: str):
    return [CorpusDocument(document_id=f"d{index}", text=text) for index, text in enumerate(texts)]


def test_unicode_tokenizer_casefolds_and_keeps_words() -> None:
    assert tokenize("Árbol, árbol; don't re-test.") == ["árbol", "árbol", "don't", "re-test"]


def test_sentence_and_paragraph_contexts() -> None:
    document = CorpusDocument(document_id="d", text="One sentence. Two!\n\nThird paragraph.")
    assert len(sentence_contexts(document)) == 3
    assert len(paragraph_contexts(document)) == 2


def test_ngram_counts_are_document_bounded() -> None:
    engine = CorpusEngine(docs("a b c", "b c d"))
    bigrams = engine.ngram_counts(2)
    assert bigrams[("b", "c")] == 2
    assert bigrams[("c", "b")] == 0


def test_association_metrics_have_expected_extremes() -> None:
    engine = CorpusEngine(docs("alpha beta.", "alpha beta.", "alpha gamma."))
    score = engine.association("alpha", "beta")
    assert score.cooccurrence == 2
    assert score.contexts_a == 3
    assert score.contexts_b == 2
    assert 0.0 < score.cosine <= 1.0
    assert score.inclusion == 1.0


def test_second_order_similarity_detects_shared_context_profile() -> None:
    engine = CorpusEngine(
        docs(
            "alpha red blue.",
            "beta red blue.",
            "alpha green yellow.",
            "beta green yellow.",
        )
    )
    assert engine.second_order_similarity("alpha", "beta") > 0.8


def test_specificity_points_to_correct_corpus() -> None:
    a = CorpusEngine(docs("apple apple orchard.", "apple tree."), name="A")
    b = CorpusEngine(docs("engine engine motor.", "engine wheel."), name="B")
    rows = {row.term: row for row in a.specificity_against(b, top_n=20)}
    assert rows["apple"].direction == "A"
    assert rows["engine"].direction == "B"
    assert rows["apple"].chi_square > 0


def test_tfidf_corpus_similarity_orders_related_above_unrelated() -> None:
    base = CorpusEngine(docs("cat sleeps on sofa", "cat eats fish"))
    related = CorpusEngine(docs("cat rests on couch", "cat eats fish"))
    unrelated = CorpusEngine(docs("quantum compiler kernel", "database transaction index"))
    assert base.compare(related).cosine_similarity > base.compare(unrelated).cosine_similarity


def test_tfidf_document_matrix_has_feature_names() -> None:
    engine = CorpusEngine(docs("alpha beta", "beta gamma"))
    matrix, features = engine.tfidf_document_matrix()
    assert matrix.shape == (2, 3)
    assert features == ["alpha", "beta", "gamma"]
