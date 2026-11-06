import numpy as np
import pytest

from app.services.errors import LLMOutputError
from app.services.rag.chunking import chunk_pages
from app.services.rag.embeddings import StubEmbedder
from app.services.rag.pdf_loader import PageText, normalize_text
from app.services.rag.quiz_service import GeneratedQuestion, evidence_is_grounded, parse_generated_payload
from app.services.common.vector_math import cosine_similarity
from app.services.gaps.clustering import centroid_of, cluster_embeddings, most_central_index


def test_normalize_text_removes_tatweel_and_control_chars():
    assert normalize_text("ال\u0640عربية\u200b  test") == "العربية test"


def test_normalize_text_collapses_blank_lines():
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


def test_chunking_keeps_page_numbers_and_sequential_indexes():
    pages = [PageText(page_number=1, text="أ" * 1500), PageText(page_number=2, text="ب" * 200)]
    chunks = chunk_pages(pages, chunk_size=1000, chunk_overlap=100)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert {c.page_number for c in chunks} == {1, 2}
    assert chunks[-1].page_number == 2
    assert all(len(c.content) <= 1000 for c in chunks)


def test_chunking_rejects_overlap_not_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_pages([PageText(1, "نص")], chunk_size=100, chunk_overlap=100)


def test_cosine_similarity_identical_orthogonal_and_zero():
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity([0, 0], [1, 0]) == 0.0


def test_cluster_groups_similar_vectors_and_separates_others():
    base = np.array([1.0, 0.0, 0.0])
    near = base + np.array([0.01, 0.02, 0.0])
    other = np.array([0.0, 1.0, 0.0])
    labels = cluster_embeddings(np.vstack([base, near, other]), min_similarity=0.9)
    assert labels[0] == labels[1]
    assert labels[2] != labels[0]


def test_cluster_handles_empty_and_single_inputs():
    assert cluster_embeddings(np.zeros((0, 3)), 0.8).size == 0
    assert cluster_embeddings(np.array([[1.0, 0.0]]), 0.8).tolist() == [0]


def test_centroid_and_most_central_member():
    vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]])
    center = centroid_of(vectors)
    assert np.linalg.norm(center) == pytest.approx(1.0)
    assert most_central_index(vectors, center) in (0, 1)


def test_evidence_must_appear_in_source_chunk():
    source = "يُعد المتجه المرجح من أهم المفاهيم في هندسة المتطلبات."
    assert evidence_is_grounded("المتجه المرجح", source)
    assert not evidence_is_grounded("مفهوم غير موجود", source)


def test_evidence_ignores_arabic_diacritics_and_spacing():
    source = "الْمُتَّجِهُ   المرجح مهم"
    assert evidence_is_grounded("المتجه المرجح", source)


def test_parse_rejects_non_json():
    with pytest.raises(LLMOutputError):
        parse_generated_payload("this is not json")


def test_parse_drops_malformed_items_and_keeps_valid_ones():
    raw = (
        '{"questions": ['
        '{"question_type": "mcq", "question_text": "سؤال صالح للاختبار؟", '
        '"options": ["أ", "ب", "ج", "د"], "correct_option_index": 1, '
        '"evidence": "نص داعم", "source_label": "C1"},'
        '{"question_type": "mcq", "question_text": "سؤال بثلاثة خيارات فقط؟", '
        '"options": ["أ", "ب", "ج"], "correct_option_index": 0, '
        '"evidence": "نص داعم", "source_label": "C1"}'
        "]}"
    )
    questions = parse_generated_payload(raw)
    assert len(questions) == 1
    assert questions[0].correct_option_index == 1


def test_parse_strips_markdown_fences():
    raw = '```json\n{"questions": []}\n```'
    assert parse_generated_payload(raw) == []


def test_mcq_requires_exactly_four_options():
    with pytest.raises(Exception):
        GeneratedQuestion(
            question_type="mcq",
            question_text="سؤال تجريبي للتحقق؟",
            options=["أ", "ب", "ج"],
            correct_option_index=0,
            evidence="دليل",
            source_label="C1",
        )


def test_true_false_forces_canonical_options():
    question = GeneratedQuestion(
        question_type="true_false",
        question_text="هل المتجه المرجح مفهوم مهم؟",
        options=["نعم", "لا", "ربما"],
        correct_option_index=0,
        evidence="دليل داعم",
        source_label="C2",
    )
    assert question.options == ["صح", "خطأ"]


def test_stub_embedder_is_deterministic_and_normalized():
    embedder = StubEmbedder(64)
    first = embedder.embed_query("هندسة المتطلبات مادة مهمة")
    second = embedder.embed_query("هندسة المتطلبات مادة مهمة")
    assert first == second
    assert np.linalg.norm(first) == pytest.approx(1.0)


def test_stub_embedder_similar_texts_score_higher_than_unrelated():
    embedder = StubEmbedder(256)
    base = embedder.embed_query("تأجيل الكويز الثاني للشعبة")
    related = embedder.embed_query("تأجيل الكويز الثاني")
    unrelated = embedder.embed_query("قاعة الحاسوب مكيفة")
    assert cosine_similarity(base, related) > cosine_similarity(base, unrelated)
