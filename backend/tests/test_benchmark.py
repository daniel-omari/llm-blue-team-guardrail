"""Unit tests for the benchmark metric calculations."""

from benchmark.run_benchmark import compute_metrics


def test_confusion_matrix_counts():
    pairs = [
        ("UNSAFE", "UNSAFE"),  # TP
        ("UNSAFE", "SAFE"),    # FN
        ("SAFE", "SAFE"),      # TN
        ("SAFE", "UNSAFE"),    # FP
    ]
    m = compute_metrics(pairs)
    assert (m.tp, m.fn, m.tn, m.fp) == (1, 1, 1, 1)
    assert m.precision == 0.5
    assert m.recall == 0.5
    assert m.accuracy == 0.5


def test_perfect_classifier():
    m = compute_metrics([("UNSAFE", "UNSAFE"), ("SAFE", "SAFE")])
    assert m.precision == 1.0 and m.recall == 1.0 and m.f1 == 1.0


def test_empty_input_is_safe():
    m = compute_metrics([])
    assert m.total == 0
    assert m.precision == 0.0 and m.recall == 0.0


def test_document_benchmark_labels_exactly_the_poisoned_chunks():
    from app.rag.documents import load_corpus
    from benchmark.run_benchmark import POISONED_CHUNKS, document_cases

    ids = {c.id for c in load_corpus()}
    assert POISONED_CHUNKS <= ids                # every poisoned id really exists
    cases = document_cases()
    assert len(cases["knowledge_base"]["UNSAFE"]) == len(POISONED_CHUNKS)
    assert cases["held_out"]["SAFE"] and cases["held_out"]["UNSAFE"]
