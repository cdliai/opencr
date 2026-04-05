import unicodedata
from dataclasses import dataclass
from enum import Enum
from collections import Counter


class ScriptDirection(str, Enum):
    LTR = "ltr"  # Latin, Cyrillic, etc.
    RTL = "rtl"  # Arabic, Hebrew, etc.
    MIXED = "mixed"  # Both present significantly
    UNDETERMINED = "undetermined"


class ScriptFamily(str, Enum):
    LATIN = "latin"
    ARABIC = "arabic"
    LATIN_EXTENDED = "latin_extended"  # Heavy diacritics (Ottoman Latinized)
    MIXED = "mixed"
    UNDETERMINED = "undetermined"


@dataclass
class ScriptAnalysis:
    direction: ScriptDirection
    primary_script: ScriptFamily
    ltr_ratio: float  # 0.0 to 1.0
    rtl_ratio: float  # 0.0 to 1.0
    arabic_char_count: int
    latin_char_count: int
    extended_latin_count: int  # Characters with diacritics beyond basic ASCII
    has_diacritics: bool
    sample_rtl_chars: str  # First few RTL characters found
    sample_ltr_chars: str  # First few LTR characters found
    detected_languages: list[str]  # Best-guess language hints


class ScriptDetector:
    """
    Detects script direction and family from OCR output text.
    Works at both page and block (paragraph) level.
    """

    # Unicode ranges for specific detection
    ARABIC_RANGES = [
        (0x0600, 0x06FF),  # Arabic
        (0x0750, 0x077F),  # Arabic Supplement
        (0x08A0, 0x08FF),  # Arabic Extended-A
        (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
        (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
    ]

    # Extended Latin characters common in Ottoman Latinized transcriptions
    OTTOMAN_LATIN_CHARS = set("ḳñāüûîâêôḫṣṭẓżḍġḳṇ")

    # Turkish-specific characters
    TURKISH_CHARS = set("çğıİöşüÇĞÖŞÜ")

    def analyze_text(self, text: str) -> ScriptAnalysis:
        """Analyze the full text of a page."""
        if not text or not text.strip():
            return ScriptAnalysis(
                direction=ScriptDirection.UNDETERMINED,
                primary_script=ScriptFamily.UNDETERMINED,
                ltr_ratio=0,
                rtl_ratio=0,
                arabic_char_count=0,
                latin_char_count=0,
                extended_latin_count=0,
                has_diacritics=False,
                sample_rtl_chars="",
                sample_ltr_chars="",
                detected_languages=[],
            )

        ltr_count = 0
        rtl_count = 0
        arabic_count = 0
        latin_count = 0
        extended_latin_count = 0
        rtl_samples: list[str] = []
        ltr_samples: list[str] = []

        for char in text:
            bidi = unicodedata.bidirectional(char)
            cat = unicodedata.category(char)

            if bidi in ("L",):  # Strong LTR
                ltr_count += 1
                if cat.startswith("L"):  # Letter
                    latin_count += 1
                    if len(ltr_samples) < 10:
                        ltr_samples.append(char)

                    # Check for extended Latin (diacritics)
                    if ord(char) > 127 and cat in ("Ll", "Lu"):
                        name = unicodedata.name(char, "").lower()
                        if any(
                            x in name
                            for x in [
                                "with",
                                "accent",
                                "cedilla",
                                "breve",
                                "circumflex",
                                "dot",
                                "stroke",
                                "tilde",
                                "diaeresis",
                                "macron",
                                "hook",
                            ]
                        ):
                            extended_latin_count += 1

            elif bidi in ("R", "AL", "AN"):  # Strong RTL or Arabic
                rtl_count += 1
                if bidi == "AL":
                    arabic_count += 1
                if len(rtl_samples) < 10:
                    rtl_samples.append(char)

        total_strong = ltr_count + rtl_count

        if total_strong == 0:
            direction = ScriptDirection.UNDETERMINED
            ltr_r = 0.0
            rtl_r = 0.0
        else:
            ltr_r = ltr_count / total_strong
            rtl_r = rtl_count / total_strong

            if rtl_r > 0.8:
                direction = ScriptDirection.RTL
            elif ltr_r > 0.8:
                direction = ScriptDirection.LTR
            elif rtl_r > 0.15 and ltr_r > 0.15:
                direction = ScriptDirection.MIXED
            elif rtl_r > ltr_r:
                direction = ScriptDirection.RTL
            else:
                direction = ScriptDirection.LTR

        # Determine script family
        has_diacritics = extended_latin_count > 5
        has_turkish = any(c in text for c in self.TURKISH_CHARS)
        has_ottoman_latin = any(c in text for c in self.OTTOMAN_LATIN_CHARS)

        if arabic_count > latin_count and arabic_count > 20:
            primary_script = ScriptFamily.ARABIC
        elif has_ottoman_latin and has_diacritics:
            primary_script = ScriptFamily.LATIN_EXTENDED
        elif direction == ScriptDirection.MIXED:
            primary_script = ScriptFamily.MIXED
        elif latin_count > 0:
            primary_script = ScriptFamily.LATIN
        else:
            primary_script = ScriptFamily.UNDETERMINED

        detected_languages: list[str] = []
        if has_turkish:
            detected_languages.append("tr")  # Modern Turkish
        if arabic_count > 50:
            detected_languages.append("ar")  # Arabic script
            if has_turkish:
                detected_languages.append("ota")  # Ottoman Turkish
        if has_ottoman_latin:
            detected_languages.append("ota-latn")  # Latinized Ottoman

        return ScriptAnalysis(
            direction=direction,
            primary_script=primary_script,
            ltr_ratio=round(ltr_r, 3),
            rtl_ratio=round(rtl_r, 3),
            arabic_char_count=arabic_count,
            latin_char_count=latin_count,
            extended_latin_count=extended_latin_count,
            has_diacritics=has_diacritics,
            sample_rtl_chars="".join(rtl_samples[:5]),
            sample_ltr_chars="".join(ltr_samples[:5]),
            detected_languages=detected_languages,
        )

    def analyze_blocks(self, text: str) -> list[dict]:
        """
        Analyze text at paragraph/block level.
        Splits by double newlines and analyzes each block.
        Useful for mixed-script documents where RTL and LTR
        sections coexist on the same page.
        """
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        results = []

        for i, block in enumerate(blocks):
            analysis = self.analyze_text(block)
            results.append(
                {
                    "block_index": i,
                    "direction": analysis.direction,
                    "primary_script": analysis.primary_script,
                    "preview": block[:100],
                    "ltr_ratio": analysis.ltr_ratio,
                    "rtl_ratio": analysis.rtl_ratio,
                }
            )
        return results


def wrap_with_direction(text: str, analysis: ScriptAnalysis) -> str:
    """Add direction hints to extracted text for proper rendering."""
    if analysis.direction == ScriptDirection.RTL:
        return f'<div dir="rtl">\n\n{text}\n\n</div>'
    elif analysis.direction == ScriptDirection.MIXED:
        blocks = text.split("\n\n")
        detector = ScriptDetector()
        wrapped = []
        for block in blocks:
            block_analysis = detector.analyze_text(block)
            if block_analysis.direction == ScriptDirection.RTL:
                wrapped.append(f'<div dir="rtl">\n{block}\n</div>')
            else:
                wrapped.append(block)
        return "\n\n".join(wrapped)
    return text
