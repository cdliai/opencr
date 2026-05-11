import pytest
from ocr_pipeline.services.text_cleaner import TextCleaner


@pytest.fixture
def cleaner():
    return TextCleaner()


class TestUnicodeNormalization:
    def test_nfc_normalization(self, cleaner):
        # Decomposed form (NFD): e + combining acute accent
        decomposed = "caf\u0065\u0301"
        result = cleaner.clean(decomposed)
        # Should be NFC: e-acute as single character
        assert "\u00e9" in result

    def test_turkish_chars_preserved(self, cleaner):
        text = "İstanbul'da güneşli bir gün. Şehir çok güzel. Doğru değil mi?"
        result = cleaner.clean(text)
        assert "İ" in result
        assert "ş" in result or "Ş" in result
        assert "ü" in result
        assert "ç" in result
        assert "ğ" in result


class TestModelTokenStripping:
    def test_strips_im_tokens(self, cleaner):
        text = "<|im_start|>Hello world<|im_end|>"
        result = cleaner.clean(text)
        assert "<|im_start|>" not in result
        assert "<|im_end|>" not in result
        assert "Hello world" in result

    def test_strips_det_tokens(self, cleaner):
        text = "Some text <|det|> more text <|/det|>"
        result = cleaner.clean(text)
        assert "<|det|>" not in result
        assert "Some text" in result

    def test_strips_grounding_tokens(self, cleaner):
        text = "<|grounding|>Convert to markdown. Some extracted text."
        result = cleaner.clean(text)
        assert "<|grounding|>" not in result

    def test_clean_removes_grounding_boxes_without_dropping_text(self, cleaner):
        text = (
            "<|ref|>text<|/ref|><|det|>[[161, 580, 667, 653]]<|/det|>\n"
            "(Yirmidokuzuncu madde) Saltanat-ı seniyenin asakir-i müs- "
            "tahfaza ikamesi hukuku."
        )

        result = cleaner.clean(text)

        assert result == (
            "(Yirmidokuzuncu madde) Saltanat-ı seniyenin asakir-i müs- "
            "tahfaza ikamesi hukuku."
        )
        assert "<|ref|>" not in result
        assert "[[161, 580, 667, 653]]" not in result


class TestArtifactRemoval:
    def test_strips_remaining_special_tokens(self, cleaner):
        text = "Text <|custom_token|> more text"
        result = cleaner.clean(text)
        assert "<|custom_token|>" not in result

    def test_strips_null_bytes(self, cleaner):
        text = "Hello\x00World"
        result = cleaner.clean(text)
        assert "\x00" not in result
        assert "HelloWorld" in result


class TestHtmlCleanup:
    def test_converts_html_table_to_plain_text_rows(self, cleaner):
        text = (
            "<table><tr><td>Köre almagan yiğittin,</td><td>Göremeyen yiğidin,</td></tr>"
            "<tr><td>Kökiregi tüyilsin.</td><td>Göğsü duralsın.</td></tr></table>"
        )

        result = cleaner.clean(text)

        assert result == (
            "Köre almagan yiğittin, | Göremeyen yiğidin,\n"
            "Kökiregi tüyilsin. | Göğsü duralsın."
        )
        assert "<table" not in result
        assert "<td" not in result

    def test_unescapes_html_entities(self, cleaner):
        text = "&quot;Yüzü de ak dana, Şarifulla&#x27;nın giydiği"

        result = cleaner.clean(text)

        assert result == '"Yüzü de ak dana, Şarifulla\'nın giydiği'


class TestWhitespaceNormalization:
    def test_multiple_blank_lines(self, cleaner):
        text = "Line 1\n\n\n\n\nLine 2"
        result = cleaner.clean(text)
        assert "\n\n\n" not in result
        assert "Line 1\n\nLine 2" == result

    def test_trailing_whitespace(self, cleaner):
        text = "Line 1   \nLine 2  "
        result = cleaner.clean(text)
        assert "Line 1\nLine 2" == result

    def test_fidelity_clean_preserves_page_spacing(self, cleaner):
        text = "Line 1\n\n\nLine 2<|im_end|>\x00"
        result = cleaner.clean_fidelity(text)
        assert result == "Line 1\n\n\nLine 2"

    def test_fidelity_clean_can_strip_grounding_boxes(self, cleaner):
        text = (
            "<|ref|>text<|/ref|><|det|>[[161, 580, 667, 653]]<|/det|>\n"
            "Visible line"
        )
        result = cleaner.clean_fidelity(text, strip_refs=True)
        assert result == "Visible line"


class TestOCRFixes:
    def test_curly_quotes_replaced(self, cleaner):
        text = '\u201cHello\u201d and \u2018world\u2019 are common.'
        result = cleaner.clean(text)
        assert '"Hello"' in result
        assert "'world'" in result

    def test_ligatures_expanded(self, cleaner):
        text = "The \ufb01rst \ufb02oor is open."
        result = cleaner.clean(text)
        assert "first" in result
        assert "floor" in result

    def test_tatweel_removed(self, cleaner):
        text = "كـــتاب"  # Tatweel (kashida) in the middle
        result = cleaner.clean(text)
        assert "\u0640" not in result


class TestEmptyInput:
    def test_empty_string(self, cleaner):
        assert cleaner.clean("") == ""

    def test_none_returns_empty(self, cleaner):
        assert cleaner.clean(None) == ""
