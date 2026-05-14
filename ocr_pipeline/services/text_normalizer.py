import re


class TextNormalizer:
    """Conservative NLP-oriented normalization for exported clean text."""

    _MARKUP_RE = re.compile(
        r"</?(center|div|span|html|body|table|tr|td|p|br|h[1-6])\b[^>]*>",
        re.I,
    )
    _LINE_HYPHEN_RE = re.compile(
        r"(?iu)([^\W\d_]{2,})-\s*\n\s*([^\W\d_]{2,})"
    )
    _INLINE_HYPHEN_RE = re.compile(
        r"(?iu)([^\W\d_]{2,})-\s{1,3}([^\W\d_]{2,})"
    )

    def normalize_for_nlp(self, text: str) -> str:
        normalized = self._MARKUP_RE.sub("", text)
        normalized = self._LINE_HYPHEN_RE.sub(r"\1\2", normalized)
        normalized = self._INLINE_HYPHEN_RE.sub(r"\1\2", normalized)
        return re.sub(r"\s+", " ", normalized).strip()
