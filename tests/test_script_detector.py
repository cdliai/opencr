import pytest
from ocr_pipeline.services.script_detector import (
    ScriptDetector,
    ScriptDirection,
    ScriptFamily,
    wrap_with_direction,
)


@pytest.fixture
def detector():
    return ScriptDetector()


class TestEmptyInput:
    def test_empty_string(self, detector):
        result = detector.analyze_text("")
        assert result.direction == ScriptDirection.UNDETERMINED
        assert result.primary_script == ScriptFamily.UNDETERMINED

    def test_none_input(self, detector):
        result = detector.analyze_text(None)
        assert result.direction == ScriptDirection.UNDETERMINED

    def test_whitespace_only(self, detector):
        result = detector.analyze_text("   \n\n   ")
        assert result.direction == ScriptDirection.UNDETERMINED


class TestLatinText:
    def test_english_text(self, detector):
        text = "This is a standard English paragraph with multiple words."
        result = detector.analyze_text(text)
        assert result.direction == ScriptDirection.LTR
        assert result.primary_script == ScriptFamily.LATIN
        assert result.ltr_ratio > 0.8

    def test_modern_turkish(self, detector):
        text = "Türkiye Cumhuriyeti'nin başkenti Ankara'dır. İstanbul en büyük şehirdir."
        result = detector.analyze_text(text)
        assert result.direction == ScriptDirection.LTR
        assert result.primary_script in (ScriptFamily.LATIN, ScriptFamily.LATIN_EXTENDED)
        assert "tr" in result.detected_languages


class TestArabicText:
    def test_arabic_text(self, detector):
        text = "بسم الله الرحمن الرحيم. هذا نص عربي طويل يحتوي على كلمات كثيرة ومتنوعة لاختبار الكشف عن الاتجاه."
        result = detector.analyze_text(text)
        assert result.direction == ScriptDirection.RTL
        assert result.primary_script == ScriptFamily.ARABIC
        assert result.rtl_ratio > 0.8
        assert result.arabic_char_count > 0


class TestMixedScript:
    def test_mixed_arabic_latin(self, detector):
        text = (
            "بسم الله الرحمن الرحيم\n\n"
            "This is the Latin section of the document with enough text.\n\n"
            "هذا القسم العربي من الوثيقة يحتوي على نص كاف"
        )
        result = detector.analyze_text(text)
        assert result.direction == ScriptDirection.MIXED
        assert result.arabic_char_count > 0
        assert result.latin_char_count > 0


class TestBlockAnalysis:
    def test_mixed_blocks(self, detector):
        text = (
            "This is an English paragraph.\n\n"
            "بسم الله الرحمن الرحيم هذا نص عربي كافي الطول\n\n"
            "Another English paragraph here."
        )
        blocks = detector.analyze_blocks(text)
        assert len(blocks) == 3
        assert blocks[0]["direction"] == ScriptDirection.LTR
        assert blocks[1]["direction"] == ScriptDirection.RTL
        assert blocks[2]["direction"] == ScriptDirection.LTR


class TestDirectionWrapping:
    def test_rtl_wrap(self, detector):
        text = "بسم الله الرحمن الرحيم"
        analysis = detector.analyze_text(text)
        wrapped = wrap_with_direction(text, analysis)
        assert 'dir="rtl"' in wrapped

    def test_ltr_no_wrap(self, detector):
        text = "This is a normal English text with enough words for detection."
        analysis = detector.analyze_text(text)
        wrapped = wrap_with_direction(text, analysis)
        assert 'dir="rtl"' not in wrapped
        assert wrapped == text


class TestTurkishDetection:
    def test_turkish_chars_detected(self, detector):
        text = "Güneş doğudan doğar, batıdan batar. Çok güzel bir gün. Şimdi öğle yemeği zamanı."
        result = detector.analyze_text(text)
        assert "tr" in result.detected_languages
