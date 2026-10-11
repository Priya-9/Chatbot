from app.i18n.translator import Translator
from app.rag.ingest import chunk_text
from app.rag.retriever import BM25Retriever, tokenize


def test_bm25_ranks_relevant_chunk_first():
    r = BM25Retriever()
    r.rebuild([
        ("pricing.md", "The Pro plan costs $12 per user per month."),
        ("security.md", "Data is encrypted at rest with AES-256 and SOC 2 certified."),
        ("refunds.md", "Annual plans can be refunded within 30 days."),
    ])
    hits = r.search("how is my data encrypted?", 2)
    assert hits[0].source == "security.md"
    assert r.search("zzzz unknown", 3) == []


def test_bm25_loads_from_database(services):
    hits = services.retriever.search("SAML single sign-on", 3)
    assert hits and any("SSO" in h.text or "single sign-on" in h.text for h in hits)


def test_tokenize_keeps_indic_words_intact():
    assert "कीमत" in tokenize("प्रो प्लान की कीमत क्या है?")


def test_chunking_respects_size_and_overlap():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(20))
    chunks = chunk_text(text, size=500, overlap=100)
    assert len(chunks) > 3
    assert all(len(c) <= 600 for c in chunks)
    assert "Paragraph 0" in chunks[0] and "Paragraph 19" in chunks[-1]


def test_translator_fallback_and_params():
    tr = Translator("locales", ["en", "es", "xx"], "en")
    assert tr.languages == ["en", "es"]  # missing locale skipped
    assert tr.t("auth.invalid_code", "es", left=2).startswith("El código es incorrecto. Intentos restantes: 2")
    assert tr.t("menu.prompt", "de") == tr.t("menu.prompt", "en")  # unknown language -> default
    assert tr.t("no.such.key") == "no.such.key"
    assert "{missing}" in Translator("locales", ["en"]).t("lead.thanks", "en", email="a@b.c").replace(
        "{lead_name}", "{missing}")


def test_all_locales_have_the_same_keys():
    tr = Translator("locales", ["en", "es", "hi", "ar"], "en")
    base = set(tr.strings["en"])
    for code in ("es", "hi", "ar"):
        assert set(tr.strings[code]) == base, code
