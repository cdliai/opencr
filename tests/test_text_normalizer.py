from ocr_pipeline.services.text_normalizer import TextNormalizer


def test_normalizer_joins_line_break_hyphenation_for_nlp():
    text = "Muahedenin müba-\ndelesi tarihinden itibaren geçerlidir."

    normalized = TextNormalizer().normalize_for_nlp(text)

    assert "mübade" in normalized
    assert "-\n" not in normalized


def test_normalizer_removes_basic_markup_for_nlp():
    text = "<center>ANKARA</center>\nBu metin kullanılabilir."

    normalized = TextNormalizer().normalize_for_nlp(text)

    assert normalized == "ANKARA Bu metin kullanılabilir."
