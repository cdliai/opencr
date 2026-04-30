import re
import unicodedata


class TextCleaner:
    """
    Post-processing and normalization
    for OCR output. All text output is UTF-8 NFC 
    normalized — critical for Turkish and Arabic diacritics.
    """

    MODEL_TOKENS = [
        "<|im_start|>",
        "<|im_end|>",
        "<|endoftext|>",
        "<|det|>",
        "<|/det|>",
        "<|grounding|>",
        "<|/grounding|>",
        "<|obj|>",
        "<|/obj|>",
        "<|quad|>",
        "<|/quad|>",
    ]

    ARTIFACT_PATTERNS = [
        re.compile(r"<\|[a-z_]+\|>"),   # Any remaining special tokens
        re.compile(r"\x00"),            # Null bytes
    ]

    # <|ref|>text<|/ref|>[[x, y, w, h]] — model reference blocks with bounding boxes
    _REF_BLOCK_RE = re.compile(
        r"<\|ref\|>(.*?)<\|/ref\|>\[\[[\d\s,]+\]\]",
        re.DOTALL,
    )

    # End-of-line soft hyphens: "word-\n" or "word- \n" followed by continuation
    _HYPHEN_RE = re.compile(r"(\w)- ?\n(\w)")

    def clean(self, text: str, strip_refs: bool = False) -> str:
        """Full cleaning pipeline."""
        if not text:
            return ""

        text = self._normalize_unicode(text)
        if strip_refs:
            text = self._strip_ref_blocks(text)
        text = self._strip_model_tokens(text)
        text = self._strip_artifacts(text)
        text = self._rejoin_hyphens(text)
        text = self._normalize_whitespace(text)
        text = self._fix_common_ocr_issues(text)
        return text.strip()

    def clean_fidelity(self, text: str, strip_refs: bool = False) -> str:
        """Minimal cleanup that preserves layout as closely as possible."""
        if not text:
            return ""

        text = self._normalize_unicode(text)
        if strip_refs:
            text = self._strip_ref_blocks(text)
        text = self._strip_model_tokens(text)
        text = text.replace("\x00", "")
        return text.strip()

    def _strip_ref_blocks(self, text: str) -> str:
        """Remove <|ref|>...<|/ref|>[[bbox]] blocks, keeping the inner text."""
        return self._REF_BLOCK_RE.sub(r"\1", text)

    def _rejoin_hyphens(self, text: str) -> str:
        """Rejoin words split across lines by soft hyphens.
        'kesin-\\nlikle' → 'kesinlikle'
        """
        return self._HYPHEN_RE.sub(r"\1\2", text)

    def _normalize_unicode(self, text: str) -> str:
        """NFC normalization — combines decomposed characters.
        Critical for Turkish ı/İ and Arabic diacritics."""
        return unicodedata.normalize("NFC", text)

    def _strip_model_tokens(self, text: str) -> str:
        for token in self.MODEL_TOKENS:
            text = text.replace(token, "")
        return text

    def _strip_artifacts(self, text: str) -> str:
        for pattern in self.ARTIFACT_PATTERNS:
            text = pattern.sub("", text)
        return text

    def _normalize_whitespace(self, text: str) -> str:
        # Replace multiple blank lines with a single blank line
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove trailing whitespace from each line
        lines = [line.rstrip() for line in text.split("\n")]
        return "\n".join(lines)

    def _fix_common_ocr_issues(self, text: str) -> str:
        # Fix common Unicode confusables in Turkish/Arabic context
        # Replace curly quotes with straight quotes in markdown context
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = text.replace("\u2018", "'").replace("\u2019", "'")

        # Fix common ligature artifacts
        text = text.replace("\ufb01", "fi")  # fi ligature
        text = text.replace("\ufb02", "fl")  # fl ligature

        # Normalize Arabic-specific characters
        # Tatweel (kashida) removal — decorative elongation
        text = text.replace("\u0640", "")

        return text
